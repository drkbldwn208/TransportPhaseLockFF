# Lean PLL build — November 20, 2026

The purpose is to recover routing/timing margin while keeping the working
feedback paths. The reference design is commit `34a0dc5`, saved before editing
under `build/PLL_LEAN/backup/`. No converter sampling, mixing, clock-distribution,
calibration, controller-gain or setpoint settings are changed.

## What stays and what goes

| Function | This build |
|---|---|
| Original 2:1 transport phase lock | Preserved, including original FRA and capture functions |
| ADC224/3 → DAC229/1 laser PLL | Preserved, including FFT acquisition, stages 0–4, gain ramps, unwrap memory, DC output and optional IIR |
| ADC225/1 → DAC229/3 laser PLL | Preserved; 3.5 GHz operation and stage-3 span of 640 turns unchanged |
| Laser-PLL FRA generators/demodulators/counters | Removed for both loops |
| Laser-PLL I/Q monitors | Removed, including their FIFOs, GPIOs, DMA3 and `pll2_iq_dma` |
| System ILA | Removed with its probe connections |
| Intensity servo | Preserved: old PI, calibrated PI/PII/PIII, lead–lag, tables, feedforward, shot recording, calibration/FRA |
| PDH tones | Preserved on DAC230/0 and DAC228/2 |
| DAC229/2 | Remains muted; the already-disabled RF-test source is replaced by constant zero/invalid inputs |

DMA3 existed before the laser PLL, but its original input was a separate
ADC224/3 beat-note I/Q recorder. It was subsequently reassigned to the new laser
PLL. It is **not** a capture from the original 2:1 transport PLL. The original
`axi_dma_0`, `axi_dma_1`, `axi_dma_2`, intensity phase-calibration `axi_dma_4`,
waveform-upload DMAs 5–7, `intensity_dma` and `intensity_shot_dma` remain.

The unused AXI interconnect slots are compacted. Surviving peripheral names,
addresses and clock domains remain unchanged. The constant `pll_fra_one` remains
because the intensity diagnostic path also uses it. Historical diagnostic RTL
and notebooks stay on disk for reference; the retired PLL monitor/FRA/RF-source
files are removed from the active Vivado source set.

## Intensity filter and latency

`intensity_rx_lowpass.sv` still suppresses the mixer sum-frequency component.
Four chronological I/Q samples arrive each 245.76 MHz fabric clock. The 180 MHz
image aliases to 65.76 MHz when those lanes are averaged; the following 15-tap
FIR rejects it. Coefficients, rounding, ADC-count scaling and lane replication
are unchanged.

The revised arithmetic is deliberately explicit:

1. Register the sums of lanes 0+1 and 2+3 (signed 17 bits each).
2. Add the two registered sums into a signed 18-bit register.
3. Multiply by the unchanged FIR coefficients, with registered products.
4. Accumulate the transposed FIR, one registered add per tap.
5. Round once, divide by four lanes and the coefficient scale, and register
   the signed 16-bit output. Replicate it onto the existing four-lane interface.

The extra pair-sum register breaks the long ADC-to-DSP input path. No intermediate
precision is discarded. Invalid samples insert zero at the same physical point;
the validity history grows by one clock so a gap invalidates the full affected
window.

| Quantity | Before | After |
|---|---:|---:|
| FIR response delay used by the previous INT2 measurement helper | 11 clocks / 44.759 ns | 12 clocks / 48.828 ns |
| Additional loop delay from this change | — | 1 clock / 4.069 ns |
| Additional phase lag at 300 kHz | — | 0.439° |
| Additional phase lag at 1 MHz | — | 1.465° |
| Passband droop at 1.5 MHz | 0.03456 dB | unchanged |
| FIR stopband, 55 MHz to Nyquist | at least 86.58 dB | unchanged |

The new calibrated intensity controller and compensator RTL were also reformatted
into separate assignments with consistent spacing and comments about the two
power scales. Their complete non-comment RTL token streams are unchanged;
PI/PII/PIII, lead–lag, anti-windup, tables and feedforward arithmetic are identical.

These delays exclude the RFDC and analog plant. Removing the PLL FRA does not
change PLL pipeline clocks: its disabled injection was combinational. When
predicting this build from a previously measured INT2 intensity plant, include
an extra `1 / 245.76e6` seconds of delay. Do not add it again to a new measurement
that already includes this build. `FAST_FEEDBACK_DELAY_S` in `intensity_servo.py`
still describes the controller/map pipeline, not this receiver filter.

## Python and operation

Use the updated `python_scripts/laser_pll.py` with the new matching `.bit/.hwh`.
The register ABI and `0xA7` version remain unchanged. `configure()`,
`channel(ol, 1)`, acquisition, DC output, tracking gains and IIR controls now work
without the removed diagnostic GPIOs. `capture_iq()` and the PLL FRA helpers
raise an explicit unavailable-feature error on this build. Older A7 builds with
those diagnostics remain usable with this control helper.

The intensity calibration notebook, manual/streamed setpoint units, sensor/AOM
mappings and PDH controls keep their existing operation. The updated intensity
capture helper records the new receiver delay in its metadata. Keep historical
helper copies alongside historical bitstreams when comparing delay metadata.

## Verification and build

Run `scripts/build_lean_pll.tcl` in Vivado batch mode with the GUI project closed.
It generates the BD, synthesizes and routes the complete project, checks setup
and hold slack, checks intensity connectivity after routing, and writes a
bitstream only after those checks pass. Artifacts are collected in
`build/PLL_LEAN/`. The user's overlay-copy monitor remains responsible for
`pynq_overlays/`; this script does not write there or program hardware.

Checks include:

- Independent integer convolution against 166,572 RTL filter samples: signed
  DC/full-scale, random input, invalid gaps, 180 MHz image and passband tones.
- Actual RF-tone simulation of both PLLs, including 800 MHz and 3.5 GHz,
  ±100 MHz frequency discrimination, amplitude changes and ADC/DAC stalls.
- Acquisition stages, remembered wraps, continuous handoffs, stage-4 ramps,
  DC output with missing ADC input and output mute.
- Comparison of all surviving BD signal connections, converter settings and
  PS addresses against the saved design, including the original 2:1 loop.
- PYNQ controls with and without the removed diagnostic peripherals.
- PYNQ metadata 0.1.5 parses all 144 remaining blocks; the ILA-free HWH
  is unchanged by the compatibility repair helper, and an inconsistent RTL/HWH
  pair is rejected. AXI clock/reset domains are checked after slot compaction.
- Intensity controller comparison over 247,244 bit-exact clocks, plus table,
  feedforward, mode-selection, output-limit and legacy-bypass tests.
- Actual AMD CIC/CORDIC simulation after the receiver FIR, including phases
  near ±π; settled phase error remains below 0.00032 rad.

Full implementation timing/utilization results are recorded in
`build/PLL_LEAN/reports/`; RTL simulation is not a timing-closure measurement.

Vivado 2024.1 crashed at synthesis launch inside the execution sandbox. Both
crash traces enter `libudev` device enumeration from the license/host-info
libraries, before synthesis starts. The build was restarted outside the sandbox
with `-tclargs resume`, using the saved, connectivity-checked design. No timing
constraints were relaxed.

## Active signal paths for debugging

```text
Original 2:1 transport PLL (unchanged):
    existing phase extractors → existing phase comparison → existing PI/NCO
    original perturbation/demodulation and DMA taps retained

Each newer laser PLL:
    real ADC → fabric DDS quadrature mixer → I/Q FIR → CORDIC atan2
        → phase/frequency error + wrap counter → acquisition/tracking selection
        → optional output IIR → DAC register → analog controllers
    raw ADC → occasional FFT estimate ────────┘

Intensity servo:
    RFDC I/Q → registered lane sums → 15-tap FIR
        ├─ original fast PI ─────────────────────────────────────────┐
        └─ selected sensor LUT → power error → PI/PII/PIII + shelf    │
                                   + feedforward → AOM inverse LUT ─┤
        selected command → existing diagnostic/output register → DAC
```

The source files most relevant to this cleanup are
`intensity_rx_lowpass.sv`, `intensity_compensator.sv`,
`intensity_linearized.sv`, `laser_pll.sv` and `laser_pll_wrapper.v` under
`TransportPhaseLockFF.srcs/sources_1/new/`. Individual arithmetic blocks retain
separate modules. The existing Python coefficient/table-loading procedures are
unchanged; the filter coefficients remain hardcoded in the RTL.

## Full routed results

The November 20 implementation passes the existing timing constraints, without
relaxing them. These are full-project results after routing and post-route
physical optimization, compared with `build/PDH_DAC230_1200_60/reports/`:

| Timing quantity | Previous build | Lean build |
|---|---:|---:|
| Worst setup slack | +0.033 ns | +0.132 ns |
| Worst hold slack | +0.001 ns | +0.010 ns |
| Worst pulse-width slack | +0.534 ns | +0.534 ns |
| Failing setup/hold endpoints | 0 / 0 | 0 / 0 |

The previous global worst setup path was the intensity ADC lane sum. The new
worst path is the first laser PLL's combined error register to its acquisition
handoff register. Setup slack is +0.505 ns for paths ending in the intensity
filter and +0.360 ns for paths starting there. Timing margin improved, but the
global +0.132 ns remains modest; this is not a promise of the same slack after
future edits or a different placement.

| Resource | Previous | Lean | Reduction | Lean / whole ZU49DR |
|---|---:|---:|---:|---:|
| LUT | 89,872 | 69,604 | 22.55% | 16.37% |
| Flip-flop | 120,983 | 87,960 | 27.30% | 10.34% |
| BRAM, 36-kbit tile equivalents | 374.5 | 300 | 19.89% | 27.78% |
| DSP | 468 | 400 | 14.53% | 9.36% |

All 148,014 routable nets are routed, with zero routing errors. DRC has no error
or critical-warning entries. Existing clock/methodology warnings and AMD CIC
DSP advisories remain; timing closure does not establish that those historical
constraints are a complete physical timing model. No board has been programmed
or measured by this build procedure.

`build/PLL_LEAN/verification.json` records bitstream/HWH hashes, source checks,
timing and resource counts. Load the matching bitstream and HWH together and
copy the updated `laser_pll.py` (or the identical `laser_pll_R7.py` alias) when
using existing control notebooks. The project can be reopened after the batch
build exits; no parallel project copy was created.
