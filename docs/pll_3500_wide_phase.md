# 3.5 GHz PLL with 640 turns full-scale phase range

This release keeps the primary ADC224/3 → DAC229/1 PLL at its existing /160
stage-3 slope. The second ADC225/1 → DAC229/3 PLL starts at **/640**, giving
approximately **±320 phase turns** at phase_gain_shift=0 with a centered DAC.
A handoff bias or analog offset can reduce the available range on either side.

The ADC remains at 1.96608 GS/s. The 3.5 GHz input has signed alias −432.16 MHz
relative to 3.93216 GHz. The existing signed reference path handles that alias;
the ADC225/0 and /2 paths and all RFDC compile-time settings are preserved.
Filtering still needs to select the physical RF band; digital processing cannot
distinguish signals in different Nyquist zones with the same sampled alias.

## What changed

`STAGE3_RANGE_SHIFT` propagates from `laser_pll_wrapper.v` through
`laser_pll.sv` and `laser_pll_error.sv` to `laser_pll_unwrap.sv`, and to
`laser_pll_tracking.sv`. It is zero on PLL1 and two on PLL2.

In stage 3 the local unwrapped phase is divided by four before the existing
phase-to-DAC scaler on PLL2. Stage 4 performs the same division after subtracting
its saved phase origin. The DAC bias, smooth coefficient ramp, 24-bit signed
turn counter and full unwrapped monitor representation remain intact. The
counter keeps accumulating beyond the DAC rails; it is not limited to 640
turns. There is no extra register, multiplier, CORDIC pass or filter. Acquisition
and tracking latency are unchanged from the preceding IS03 design.

Previously reserved phase-status bits [26:23] report this range shift. The
helper reads them through `stage3_phase_divisor(target)`. Old A7 hardware reports
zero, meaning 160. The global Python constant 160 is the legacy base, not the
range of every PLL. Firmware version remains A7; use the matched HWH and helper.

## Operation

Use `laser_pll_3500MHz.ipynb` for a compact secondary-channel workflow, with
`ol` as the existing overlay and `target = laser_pll.channel(ol, 1)`. The normal
acquisition stages, analog-controller procedure, GPIO gains and I/Q capture
remain available. Stage 3 requires valid phase but no frequency-excursion gate.
It does not detect optical lock automatically.

| Stage-4 shift | Relative sensitivity | Full DAC phase span | Nominal centered range |
|---:|---:|---:|---:|
| 0 | 1× | 640 turns | ±320 turns |
| 1 | 2× | 320 turns | ±160 turns |
| 2 | 4× | 160 turns | ±80 turns |
| 3 | 8× | 80 turns | ±40 turns |
| 4 | 16× | 40 turns | ±20 turns |

Enter tracking after confirming stage-3 lock, at shift zero. Increase or decrease
shift one step at a time; the saved operating point is preserved and gain is
ramped. This prevents a static bias jump but cannot guarantee stability after
increasing loop gain. Keep the analog headroom and stability checks used for
the primary loop. A 1 MHz sustained detuning still reaches ±320 turns in 320 µs
from center; Python polling cannot prevent that.

The weaker base slope enlarges the acquisition range by reducing volts/radian.
It does not average phase or improve the intrinsic CORDIC/ADC phase estimate.
At a nominal 2 Vpp DAC span, shift zero gives about 0.497 mV/rad; shift two
restores the primary loop's /160 slope, about 1.989 mV/rad.

## Verification

The new RTL test drives actual wrapped phase through ±1024 turns and checks
full phase retention, correct clipping/scaling, ±300-turn linearity in tracking,
all gain shifts, preserved bias and unchanged pipeline timing. The end-to-end
stage test now runs both the primary 800 MHz input and the signed-alias second
PLL at 3.0, 3.45 and 3.5 GHz. Both pass, along with the previous handoff/scaler
and Python controls tests. Full routed timing and resource results are recorded
in the release's `verification.json` and `reports/`; simulation alone is not a
hardware timing or optical-lock test. No FPGA programming or laser test was
performed here.
