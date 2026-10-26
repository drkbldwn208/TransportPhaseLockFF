# Intensity calibration and frequency response — measurement release

This release adds measurements to the existing ADC224/1 → fast PI → DAC228/3
intensity servo. The user specified an 80 MHz AOM carrier and approximately the
full positive DAC-amplitude range. The existing RFDC configuration, PI algorithm,
32-bit setpoint streamer, both laser PLLs, their FRAs, and their I/Q captures remain
present. No sensor or actuator compensation table is applied to live feedback.
The separate feature signature is `0x494E5401`; the laser PLL ABI remains A7.

## What to connect

```
DAC228/3, existing 80 MHz carrier → RF amplifier → AOM
stabilized optical output → PDA36A2 → ZAD-1+ IF
DAC228/1, existing mixer LO (normally 90 MHz) → ZAD-1+ LO
ZAD-1+ RF → ADC224/1 → RFDC I/Q demodulation → existing fast PI
```

Use a power meter on that output or a fixed pickoff for the sensor calibration.
Keep detector gain, LO amplitude/phase, ADC mixer settings and cabling fixed.
The PI uses the I quadrature, not magnitude. A change of LO phase therefore
changes the sensor calibration. Software restores only a deliberately saved
working setup; it does not invent RF phases or stable controller gains.

## Physical quantities and identifiability

Assume P=A(t)F(u), with sensor offsets removed and a repeatable static actuator
curve. A short record at mean command u0 gives Q=A F'(u0) U and P0=A F(u0), hence

```
K(f,u0) = Q/(P0 U)          [1/DAC code]
k(u0) = d ln(F)/du          [1/DAC code], only on a quasi-static plateau
```

U is the measured modulation of the actual limited DAC command. It is not the
programmed dither amplitude. C is the selected PI command before injection,
D=U-C is the actual injected modulation. For negative feedback C=-L U:

```
L = -C/U                   full return ratio, dimensionless
S = U/D                    sensitivity
Q/U                        calibrated optical plant response, power/code
```

L includes the current raw-sensor PI, digital filtering, converters, RF driver,
AOM, detector and mixer. Q/U includes the actuator and sensor/receive dynamics
between the digital injection and observation points. Static sensor correction
does not remove detector/mixer bandwidth. No propagation delay is silently
subtracted from K. Measure a flat, nearly real plateau, or explicitly justify
and save a complex dynamic correction. Retain negative k on a falling branch;
never use abs(K) as its signed static slope.

Unknown incident power cancels only under the multiplicative model. Additive
optical background, coherent upstream modulation at the test frequency, thermal
memory, alignment changes and bad sensor calibration do not cancel. Revisit the
same command under different incident power; incompatible slopes cannot be
integrated into a single F. This measurement alone cannot prove those assumptions.

## Acquisition, nonlinear sensor correction and averaging

The new diagnostic adds a ramped cosine after the existing PI/manual selection
and before the existing DAC formatter. It clamps the total command to programmable
limits while the tone is active; the default is 0…32767. A boundary register after
the existing PI/manual selection adds **one feedback clock, 4.069 ns**, in both
idle and diagnostic modes. At idle it preserves the command value with this
fixed delay. The initial unregistered path failed routed setup by 0.148 ns: the
HLS PI's output saturation and the new add/limit logic were in the same clock.
The register separates those operations without changing the PI arithmetic.
Its extra phase lag is 0.146° at 100 kHz and 1.465° at 1 MHz. Measured L includes
this delay; no software delay correction is needed or silently applied.
The PI's original four-I-lane average, one-pole IIR, gains, anti-windup and limits
are unchanged. Its integrator does not know about the diagnostic adder's limits,
so clipped records are rejected and large dither should be avoided.

The DMA records four raw I samples from the same ADC word, C, U and the aligned
DDS phase. There is **no new temporal averaging or antialias filter before this
capture**. Frames are selected once every 2^D fabric clocks. This deliberate
choice permits applying a nonlinear sensor calibration to each individual lane
before any new averaging, as required by the calibration method. Correcting an
already-averaged nonlinear sensor signal generally gives a different answer.

Python interpolates the calibrated sensor map on every raw lane, then averages
the four corrected samples in that word. Their total span is about 3.05 ns at
the existing 983.04 MS/s complex ADC output. At these modulation frequencies
they represent a single observation; the small fixed timestamp convention and
the RFDC/analog delays belong to the measured response. Frame selection does
alias out-of-band noise and harmonics. Repeat at twice the capture rate and
nearby frequencies: long averaging does not cure systematic aliasing. The
original RFDC decimation filter remains in place, but is not an antialias filter
for arbitrarily large additional frame decimation.

For each of C, U and P, fit

```
x(t)=x0+x1*(t-tc)+xc*cos(theta)+xs*sin(theta)
X=xc-i*xs
```

theta is the recorded DDS lookup phase, aligned to the injected command. Fits
include DC and linear drift instead of assuming an integer-cycle sum eliminates
them. Windows are approximately integer-cycle, with at least 16 samples/cycle.
Default blocks contain at least 16 cycles and 20 ms, followed by repeated blocks;
the 10 Hz default is about 1.6 s. The sample-rate floor is at least 250 kS/s
(typically 480 kS/s due to power-of-two selection). At 1 MHz it is 30.72 MS/s.
Each block has at most 1,048,575 records (approximately 16 MiB).
The notebook's 61-point sweep with eight blocks per point produces about 0.86 GiB
before NPZ compression (up to about 2.57 GiB at 24 blocks). Its minimum acquisition
and settling time is about two minutes; board-side fitting, compression and DMA
overhead add to this. Use a fresh output filename for each sweep.

Use short blocks consistent with adequate cycle count; the default rejects
fitted optical drift above 3% and fitted command drift above 2% of mean command
per block. Feedback can hold P fixed while upstream drift changes u, so both
checks matter. These thresholds are initial criteria,
not proof of negligible bias. Check shorter blocks and amplitude dependence.
The illustrative 0.5–2% optical modulation target must be verified from Q/P0;
32 command codes is only a starting probe amplitude. Select a calibration band
above dominant drift but below the measured actuator and detector rolloffs.
Lower calibration-loop bandwidth only deliberately, with known stable settings.

Sweep averages complex C and U before taking -C/U. For K, it averages Q/P0 across
blocks and divides once by mean U, avoiding an average of noisy-denominator
ratios. Per-block K is retained for binning by actual u0. Repeat scatter provides
complex uncertainties, including covariance through response residuals. Single
block fit uncertainties assume white residuals and can underestimate correlated
noise. Separate `loop_reliable` and `plant_reliable` flags require resolved
numerators and denominators; `reliable` requires both. High loop gain can still
make U unresolvable. Repeated blocks are not necessarily statistically independent.

## Sensor and AOM table workflow

1. Save a known working, nonzero manual-setpoint setup before reprogramming.
   The notebook can attach to an already loaded matching image without download.
   Hardware download resets all loops; integrator/streamer memory is not restored.
2. Take a dark/electronic-offset capture with fixed detector/mixer settings.
   Assign zero offset-corrected optical power at its measured raw ADC count.
3. Set manual optical targets and record power-meter readings and raw ADC samples.
   Build a monotonic counts→power map. Cover later noise/dither excursions;
   extrapolation is rejected. Absolute units may be arbitrary but consistent.
4. Measure small-signal FRA at fixed optical setpoint. Check half amplitude,
   capture-rate convergence, drift, clipping and actual U before interpreting L.
5. Choose a quasi-static calibration frequency based on measured K, not solely
   the loop crossover. The notebook's 1 kHz is explicitly an illustrative value.
6. Scan and revisit manual setpoints; sort by measured mean DAC command u0.
   Compare overlapping command bins and nearby modulation frequencies before
   accepting signed real slopes. Filling gaps is preferable to extrapolating.
7. Bin k(u), preserving sign and empirical scatter. Integrate trapezoidally:
   ell[i+1]=ell[i]+(k[i]+k[i+1])*(u[i+1]-u[i])/2. Export F=exp(ell-max(ell)).
8. Invert a single monotonic branch with piecewise-linear interpolation. The
   table is exported as floating and rounded DAC codes within the calibrated
   range. This release does not engage it. Live enable with preserved operating
   point, controller rescaling and an independent dither-before-table test
   (dP/P≈dv/v) belong to the later compensation implementation.

The notebook intentionally makes setpoint choices and quasi-static acceptance
explicit. It leaves the final manual setpoint selected after a scan. A dark
record may legitimately have a rail flag; transfer measurements exclude rails.

## Register and data format

| IP | Address | Channel 1, offset 0 | Channel 2, offset 8 |
|---|---|---|---|
| intensity_control | 0xA0310000 | control | status |
| intensity_tone | 0xA0320000 | unsigned DDS frequency word | signed amplitude in low 16 bits |
| intensity_limits | 0xA0330000 | min in low 16, max in high 16 | signature 0x494E5401 |
| intensity_counts | 0xA0340000 | actuator-clip clock count | invalid-input clock count |
| intensity_dma | 0xA0350000 | standard AXI DMA S2MM registers | — |

Control: bit 0 tone enable, bit 1 capture arm, bits 7:3 D, bits 31:12 record count.
Status: bit 0 collecting, 1 last record accepted into FIFO, 2 overflow, 3 invalid
input, 4 actuator clipped, 5 PI at 0/32767, 6 ADC near a rail, 7 tone ramping,
8 tone active including ramp-down tail, 9 diagnostic settings changed, 31:12
records queued. Flags/counts cover every fabric clock during capture, including
between saved frames, and reset on disarm. They are copied to the raw NPZ first.
The 32-bit clock counters wrap after about 17.48 s of counted events; the sticky
fault flags remain set. Default blocks are shorter than this.
The existing DAC228/3 stream has no TREADY signal; the diagnostic readiness input
is tied high. This release cannot count physical DAC stalls on that interface.
The invalid-input flag therefore detects ADC valid gaps in the integrated design.

One little-endian record is 16 bytes / four uint32 words:

| Word | Bits | Meaning |
|---|---|---|
| 0 | 15:0 / 31:16 | signed raw I lanes 0 / 1 |
| 1 | 15:0 / 31:16 | signed raw I lanes 2 / 3 |
| 2 | 15:0 / 31:16 | signed C / signed U, DAC command codes |
| 3 | 31:0 | unsigned phase, 2^32 = one turn |

Raw NPZ: `raw`, `sample_rate_hz`, `decimation_log2`, `status`, `clip_samples`,
`invalid_samples`, `metadata_json`. Metadata includes source operating settings,
calibration table and frequency plan. Every sweep creates a directory of raw
NPZs, an aggregate CSV, `_blocks.csv`, and a setup JSON. Aggregate rows include
actual frequency, complex C/U/Q/D/L/K as `_re`/`_im`, P0, u0, repeat counts,
uncertainties and reliability. K units are inverse DAC code; Q uses calibrated
power units. Without a sensor table K is NaN, rather than mislabeled optical data.
If a hardware-flagged block leaves the sensor table, its optical fit is NaN and
the block is excluded while retries continue. An unflagged out-of-range record
stops the sweep so the calibration can be extended; no extrapolation is hidden.

## Module walkthrough and timing

`intensity_tone.sv`:

- Ports take fabric clock, enable, 32-bit FCW and signed 16-bit amplitude.
- The 4096-entry signed cosine ROM is Q1.15. FCW gives f=word*245.76 MHz/2^32,
  resolution 0.05722046 Hz. The ROM angle grid is 2*pi/4096=1.534 mrad.
- `envelope` is 0…4096; one step each 64 clocks gives a 1.0667 ms on/off ramp.
- Clocked stages read cosine, multiply amplitude, multiply envelope, then shift
  by 27 bits into signed command codes. Four stimulus registers do not delay PI.
- The corresponding lookup phase travels through the same stages. The tail
  shift register keeps the active flag asserted until old stimulus has drained.

`intensity_probe.sv`:

- Registers the selected manual or PI command for one clock, instantiates the
  independent DDS, adds its signed dither and applies the configured limits.
  Recorded C is this registered command, immediately before injection; U and
  DDS phase are simultaneous with it. This includes the new register in -C/U.
- Idle bypass preserves the command's signed value with the same one-clock delay
  as diagnostic operation. The DAC formatter and RFDC interpolation are unchanged.
- Capture arm resets only the new FIFO and capture state. A rising arm latches
  frame spacing/count and settings for the configuration-change check.
- ADC-valid, ADC-rail, PI-rail and actuator-clip checks cover every capture clock,
  independent of frame spacing. Counters measure fabric clocks. A separate ADC
  register allows the rail comparator to meet timing; its window is delayed too,
  so it checks the exact original interval and drains the last checked sample.
  It does not delay raw ADC capture or the feedback data.
- At each frame boundary it packs raw lanes, simultaneous C/U and aligned phase.
  It holds an unaccepted AXIS word; if a new frame cannot be queued it sets an
  overflow flag rather than stalling feedback. Such records must be rejected.
- The last record asserts TLAST. Queued length and DMA completion are both
  checked by Python. Disarming clears the observer without resetting the PI.

`intensity_probe_wrapper.v` is the Verilog port boundary for Vivado module-reference
and AXIS inference. It has no datapath registers. The new FIFO and DMA are readout
only. ROM initialization and frame alignment are tested in RTL simulation.
A separate test instantiates the generated Xilinx FIFO netlist and verifies
reset/rearm, uniform frame spacing at D=3 and D=8, DMA backpressure, and TLAST.

Verification includes synthetic nonlinear sensors, incident-power scaling,
linear drift, known delay/sign, calibration-before-average ordering, unresolved
denominators and signed inverse reconstruction. These are software/RTL checks,
not a physical AOM measurement. Final routed timing/resource results are in the
release `verification.json` and reports; no hardware is programmed by the build.

For incremental rebuilding, the scripts explicitly use the `TimingClosure`
directive, which targets zero slack even when the reference checkpoint failed
timing. The default `RuntimeOptimized` directive can instead target the seed's
negative slack. This changes implementation effort, not clock constraints.
See [AMD's incremental target-WNS documentation](https://docs.amd.com/r/2024.1-English/ug1387-acap-hardware-ip-platform-dev-methodology/Incremental-Directives-and-Target-WNS).
