# Filtered intensity receiver and 3.5 GHz PLL — INT2 / A7

This release removes the intensity receiver's 180 MHz mixer product before it
reaches the PI, phase calibration and intensity measurement. It also supports
ADC225/1 → DAC229/3 phase locking at 3.5 GHz. It does not load a calibration table
into live feedback or change the PI equations.

## Files and notebook entry points

Install `TransportPhaseLockFF.bit` and `TransportPhaseLockFF.hwh` together, with
the same filename stem. Update `intensity_calibration.py`,
`intensity_phase_calibration.py` and `laser_pll.py` from this package; its
`laser_pll_R7.py` is an identical compatibility copy for notebooks using that
import name. Reload imported modules after replacing them. The A7 version alone
does not distinguish this build from older R7 images:

```python
assert ol.pll_acquisition_status.read(8) >> 24 == 0xA7
assert ol.intensity_limits.read(8) == 0x494E5402
```

Use `intensity_phase_calibration.ipynb` for DC-input phase alignment, then
`intensity_calibration.ipynb` for optical sensor calibration and intensity FRA.
The latter includes clock/overlay loading, saving/restoring the working
intensity settings, reusing a sensor table, and measurement/export instructions.
Loading a bitstream resets running loops; attaching with `download=False` only
works with the matching already-loaded image and HWH. No FPGA download is needed
merely to refresh a helper in an attached notebook.

### HWH loading correction, 2026-10-28

The original INT2 HWH caused PYNQ `WrongPolarityConnection` between
`system_ila_0/SLOT_0_AXIS` and `SLOT_5_AXIS`. These unused debug inputs were
connected to each other in metadata, with no source; the implemented bitstream
ties them to zero. This was a release verification omission. The preceding
`No cached metadata present` message was not the cause.

The corrected HWH in this package removes only those inactive debug connections;
the `.bit`, register map, PI/calibration DMA paths and timing are unchanged.
Replace the HWH beside your existing INT2 bitstream, or copy `repair_int2_hwh.py`
to the notebook directory and run:

```python
from pathlib import Path
from repair_int2_hwh import repair_hwh
bit_path = Path('/home/xilinx/Bitfiles/FreqLocksBranch/overlays/TransportPhaseLockFF.bit')
print(repair_hwh(bit_path.with_suffix('.hwh')))
```

This only edits the HWH and saves a backup; it does not touch running hardware.
Then rerun your usual overlay-loading/setup cell. The repair accepts only the
affected release (or its already-corrected HWH), checked by SHA-256. No package
upgrade or cache deletion is required for the reported error. Metadata parsing
is now tested with Python 3.10 and `pynqmetadata==0.1.5`; the original reproduces
the exact error and the repaired file parses successfully. This is a host-side
test, not an FPGA download.

Corrected HWH SHA-256:
`5f130cfe0e594110bb8ea1677a9fa80174caa42bdc8506ca8a4c4fcf07f6e667`.
The raw Vivado HWH is preserved in `source/metadata/` for provenance. The user's
shell monitor still owns `pynq_overlays`; an already-copied HWH there or on the
board needs the same repair/replacement. No bitstream files are moved by this fix.

## Intensity filter and pipeline

The existing 90 MHz LO, ADC224/1 RFDC mixing/decimation and 80 MHz AOM carrier
are retained. Four complex RFDC samples arrive each 245.76 MHz clock, representing
983.04 MS/s. A real mixer produces both the desired baseband signal and a 180 MHz
image. The old four-lane average and PI IIR did not adequately reject that image.

`intensity_rx_lowpass.sv` first sums the four consecutive I samples and the four
Q samples. It retains the two fractional bits of each mean until final rounding.
Each quadrature then passes through a 15-tap, symmetric FIR at 245.76 MS/s.
Coefficients are positive integers divided by 262144; their sum is exactly one:

```
243, 1423, 4698, 11113, 20616, 31342, 39982, 43310,
39982, 31342, 20616, 11113, 4698, 1423, 243
```

The coefficients were obtained with SciPy `remez(15, [0, 1.5e6, 55e6, 122.88e6],
[1, 0], weight=[1, 50], fs=245.76e6)`, normalized to unity DC gain, rounded to
18 fractional bits, and corrected at the center tap so the integer sum is exact.
The **quantized** response, not just the design target, is checked in simulation.
Coefficients are fixed RTL constants in this release. There is no PS coefficient
reload or receiver bypass; changing the filter requires a rebuilt bitstream.
Image rejection is specified for the existing 90 MHz LO and its nearby modulation
sidebands; a substantially different LO can move the image outside this stopband.

| Property | Value |
|---|---:|
| DC gain | exactly 1 |
| Maximum droop, DC–1.5 MHz | <0.035 dB (about 0.40% amplitude) |
| FIR stopband, 55–122.88 MHz | >86 dB rejection |
| 180 MHz image after lane averaging | aliases to 65.76 MHz, inside stopband |
| Added low-frequency feedback delay | 11 clocks = 44.759 ns |
| Added phase lag at 100 kHz / 1 MHz / 1.5 MHz | 1.61° / 16.11° / 24.17° |
| DC rounding | nearest integer ADC count; constant integer inputs exact |
| Step overshoot from this FIR | none: coefficients nonnegative, sum one |

The delay is relative to the previous receiver, including the four registered
arithmetic boundaries below. The existing four-lane averaging time convention
is common to both paths. The A7 intensity-output boundary register already
present in the previous release remains unchanged.

| Step | Operation | Pipeline registers |
|---|---|---:|
| 1 | Signed sum of four lanes, 18 bits | 1 |
| 2 | Multiply by 18-bit coefficients, 36-bit products | 1 |
| 3 | Transposed FIR: one 36-bit add/register per tap | 1 plus FIR history |
| 4 | Round, divide by 4 × 262144, return to 16-bit ADC units | 1 |
| FIR group delay | Seven sample intervals | 7 |

The filtered I sample is replicated into four lanes to preserve the existing
HLS PI input format. Its internal average therefore returns the same filtered
sample. PI enable, bias, setpoint counts, Kp/Ki encoding, integrator/anti-windup,
limits and 32-bit FCW streamer remain the same. Static setpoint-to-optical-power
calibrations can be reused with unchanged LO/sensor/bias settings. Recheck an
optical calibration point after phase alignment. The added delay changes the
high-frequency loop response; unchanged gains are not a guarantee of stability.
Oscillations at a few hundred kHz are inside the passband: this filter does not
remove genuine loop ringing there. Use the FRA and controller gains to address
that separately from the 180 MHz mixer image.

The intensity DMA also records four copies of filtered I, not four independent
raw ADC samples. Frame width, C/U commands, DDS phase and addresses are unchanged.
Its feature signature is now **0x494E5402**. The updated helper refuses INT1 live
hardware; historical raw NPZ data can still be analyzed offline. New captures
save the filter identity, feature version and added delay. Raw ADC rail detection
uses a separate unfiltered bus, so averaging cannot hide input clipping.

This is an RF-image rejection filter, not a complete antialias filter for every
programmable DMA decimation. Other signals above the selected capture Nyquist
frequency can still alias. Compare two capture rates and keep optical excursions
inside the measured sensor table. Do not extrapolate the table to accommodate
an RF image. The sensor map now acts on the recovered baseband sensor value.

## Calibration phase monitor

The existing slow phase monitor now uses:

```
filtered I/Q → existing four-lane formatter → matched I/Q CICs (8192×)
             → CORDIC atan2 → existing packetizer → axi_dma_4
```

Both three-stage CICs retain all 55 internal bits and run from the same clock
and valid input. Their 8192^3 gain is removed only at the output, by selecting
bits 54:39. The old Hogenauer truncation discarded five input bits (32-count
steps), which also biased small quadratures; it is no longer used here. The phase DMA remains 16-bit signed radians, 8192 codes/rad, at
30 kS/s. The additional slow averaging is only in the calibration monitor,
not in the feedback path. In the released INT2 bitstream, ILA slots 0, 1 and 5
are tied to zero because interface connections did not override scalar wiring.
Slot 4 observes the packetized calibration phase during an `axi_dma_4` capture;
the calibration DMA itself is connected correctly. The setup Tcl now explicitly
wires slots 0/5 to phase and slot 1 to filtered I/Q for the next build. The HWH
repair does not restore those physical probes in the existing bitstream.

Averaging wrapped angles after atan2 was invalid near ±π. The new averaging
order removes that bias. Use `intensity_phase_calibration.ipynb`: a stable positive
IF DC source, feedback disabled, unchanged ADC/LO frequencies, read phase, add
its residual to the existing correction, and verify a small residual. The helper
uses two's-complement encoding, a circular mean and a buffer with room for the
legacy packetizer's first N+1-word packet. It reports a moving phase instead of
silently accepting it. It does not configure or reset RFDC mixers.

## Second PLL at 3.5 GHz

The ADC rate remains 1.96608 GS/s. Physical 3.5 GHz is in Nyquist zone 4 and has a
signed alias of **−432.16 MHz**. A positive-frequency DDC would reverse the RF
phase. The helper instead programs the existing fabric DDS with a negative
48-bit frequency, retaining the physical RF phase and ref-minus-beat sign.
The FFT estimator still reports positive frequency; its acquisition error now
mirrors that bin when the reference is negative. No register is added to either
PLL's fast error path.

Only ADC225/1's Nyquist parity default changes from odd to even. The driver uses
`NyquistZone=2` for even zones, not literal 4; see
[AMD XRFdc_SetNyquistZone](https://docs.amd.com/r/en-US/pg269-rf-data-converter/XRFdc_SetNyquistZone).
The helper selects even/odd parity for the chosen physical frequency while muted.
Calibration mode remains 2. Adjacent ADC225/0 and /2, tile rates and all DAC rates
are unchanged. Hardware RF input bandwidth/SNR and the analog controller must
still be validated on the bench.

```python
import importlib
import laser_pll
laser_pll = importlib.reload(laser_pll)
# ol has the matching loaded bit/HWH; this selects handles without changing loop 1.
ol2 = laser_pll.channel(ol, 1)
reference_hz = laser_pll.configure(ol2, reference_frequency_hz=3.5e9,
    phase_gain_shift=0, capture_gain_shift=6, minimum_amplitude=64, invert=True)
laser_pll.configure_acquisition(ol2, stage=1)
print(reference_hz, laser_pll.acquisition_status(ol2))
# Enable and proceed through the same existing acquisition/tracking workflow.
# laser_pll.enable(ol2)
# laser_pll.select_stage(ol2, 2)
# laser_pll.select_stage(ol2, 3)
```

±100 MHz around 3.5 GHz remains within the same zone and existing fine-capture
band. RTL tests use physical 3.4/3.5/3.6 GHz real tones, checking phase and
frequency-error signs; coarse FFT-bin polarity is separately tested. The coarse
FFT searches sampled 200–960 MHz, corresponding approximately to physical
2.97216–3.73216 GHz in this zone. A tone across a folding boundary is ambiguous;
the FPGA cannot determine its physical RF band from real samples alone.

The new helper also retains the former 4.4 GHz band. Changing zone parity while
enabled is rejected: mute/reconfigure that loop first. Reference changes within
a zone retain phase continuity. FFT status reports physical frequency using the
current DDS sign. Use the supplied helper with the rebuilt bit/HWH.

## Functionality retained and verification

Both PLL loops, their long I/Q captures, capture/tracking gains, optional lead–lag
compensators, closed-loop FRA and RF phase-modulation FRA remain present. Intensity
manual/streamed setpoints, output dither, FRA and calibration exports remain.
No experiment hardware is programmed by the build scripts.

`tests/test_intensity_rx_lowpass.py` compares 166,572 RTL output samples with an
independent integer convolution, including negative/full-scale DC, image tones,
phases near ±π, passband tones, random data and validity gaps. Additional tests
cover actual AMD CIC/CORDIC calibration models, signed PLL tones, acquisition
handoffs, FIFO operation, software units and notebook execution. Full-board routed
timing and routed connectivity are reported separately in the release package;
RTL simulation is not a substitute for place-and-route timing or an optical test.

### Routed results, 2026-10-28

The completed full-board implementation meets the project's existing timing
constraints: **WNS +0.016 ns, WHS +0.001 ns, pulse-width slack +0.534 ns**, with
zero failing endpoints in each category. The filter uses **101 LUTs, 50 fabric
flip-flops, 30 DSPs and no BRAM** (0.70% of the device's DSPs). Whole-board usage
is 84,456 LUTs, 114,026 fabric flip-flops, 417 DSPs and 353 BRAM36 equivalents.

The routed connectivity audit checks the actual RFDC → filter → PI drivers.
Synthesis removes redundant connections from the four identical PI input lanes;
the audit verifies every remaining connection and all 16 distinct sample bits.
No source or pipeline change was needed to close timing.

Existing clock/external-I/O constraint warnings remain. The AMD CIC cores also
report the dynamic-PCIN placement warning AVAL-318 (already present on the old
I calibration CIC). The two DSP sites immediately below the flagged CIC cells
are unoccupied in this routed design; `reports/intensity_cic_dsp.rpt` records
that placement and the OPMODE drivers. These warnings are retained in the DRC
reports, not suppressed. No hardware download or physical optical-lock test has
been performed.
