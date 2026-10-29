# Optional LUT compression analysis — no hardware changes

The current bitstream keeps the direct tables, as requested. This offline
comparison quantifies a possible later replacement. It does not modify the
calibrations, controller helpers, notebook, RTL, or block design.

Direct storage contains 192 KiB of logical data: two 16384×16 sensor tables
and one 65536×16 actuator table. The implementation uses 48 BRAM36 blocks
(4.44% of 1080 on this device), including the physical RAM packing overhead.
The attraction is predictable lookup latency and no interpolation multiplier.

## Calculation

Every integer ADC input inside each measured calibration interval and every
integer transmission index up to the measured actuator cap were evaluated.
The interpolation stores a rounded 16-bit base and 16-bit difference between
neighboring rounded endpoints. It computes

```
y = base + ((delta * fraction + stride/2) >> log2(stride))
```

This is a hardware-realizable multiply/add/shift, not floating-point
interpolation. The reference sensor map is the measured piecewise-linear
calibration; the actuator reference is asin(sqrt(F))/alpha. Dense-table
quantization is separately included in the comparisons. The CSVs retain
maximum and RMS errors and the worst input address.

A uniform sensor grid must handle the calibrated endpoints carefully.
Simply sampling the current clamped table rounds the end of the calibration
into an artificial flat segment. For example, stride64 gives up to 0.631 mW
high-mode error at the first calibrated ADC value. The better comparison
uses the first/last measured slope to form just the adjacent guard endpoint;
only inputs within the measured ADC interval are evaluated. This is not
permission to use uncalibrated ADC values. Values beyond the last guard node
are constant and all stored nodes fit unsigned16.

## Sensor-map errors

These figures include endpoint rounding and integer interpolation, using the
guard endpoints described above. Maxima were checked at every valid ADC count,
including the measured calibration knots.

| Intervals per sensor mode | ADC stride | Both modes, estimated BRAM36 | Low-mode max error | High-mode max error |
|---|---:|---:|---:|---:|
| 256 | 64 | 1 | 5.06 µW | 55.18 µW |
| 512 | 32 | 1 | 3.89 µW | 33.82 µW |
| 1024 | 16 | 2 | 3.10 µW | 6.57 µW |

The high-mode maximum for256/512 intervals occurs at ADC110, a measured
calibration knot: this is real smoothing of the calibration's slope change,
not a plotting artifact. At1024 intervals, the high-mode maximum occurs at
ADC3685. The1024-interval implementation differs from the current dense
output by at most one common-power code in low mode and two in high mode.
One power code is3.052µW at the common200mW full scale.

## Actuator-map errors

The measured command interval is1119.39–21335 codes. Values below that interval
remain unvalidated model extrapolation even if interpolation is numerically
accurate. The final command is clamped to21335. Guard endpoints around the cap
are sampled from the unclipped inverse, then the interpolated output is clamped;
pre-clipping those endpoints would introduce a premature bend below the cap.

| Uniform intervals | F-index stride | BRAM36 estimate | Max error in measured range | Max error for u≥4000 | Max error including dark end |
|---|---:|---:|---:|---:|---:|
| 512 | 128 | 1 | 16.94 codes | 1.02 codes | 234.30 codes |
| 1024 | 64 | 1 | 3.38 codes | 0.99 codes | 165.43 codes |
| 2048 | 32 | 2 | 1.16 codes | 0.98 codes | 117.01 codes |
| 4096 | 16 | 4 | 0.99 codes | 0.99 codes | 82.47 codes |

The large near-zero error is the square-root shape, not a phase or control
issue. A short dense prefix removes it:

| Dense prefix | Remaining F stride | Max error over all valid indices | Difference from existing dense table | Optical error at A_eff=184mW |
|---|---:|---:|---:|---:|
| Indices0–255 | 64 | 2.48 DAC codes | ≤2 codes | ≤8.45 µW |
| Indices0–255 | 32 | 1.02 DAC codes | ≤1 code | ≤7.89 µW |

Index0 remains exactly zero. The dense prefix extends to approximately1322
DAC codes, covering the dark-end curvature and passing the smallest measured
command of1119 codes.
The optical errors are `A_eff*(sin²(alpha*u_interpolated)−F_requested)`, not a
new calibration of incident power. They scale linearly with A_eff. Near u≥4000,
these numerical errors are much smaller than the measured AOM/sensor model
uncertainties.

## Possible later hardware tradeoff

A straightforward candidate is1024 intervals per sensor bank plus the
256-entry actuator prefix and stride32 tail. Estimated resources are:

- Two BRAM36 for the two32-bit sensor base/delta banks combined.
- Two BRAM36 for the actuator tail; its prefix can use about64 LUT6 of
  distributed RAM, or one additional BRAM36.
- About two DSP48 blocks, one sensor interpolation and one actuator interpolation.
- Approximately two to four additional registered clocks across both maps,
  depending on whether the existing output register can be reused. At245.76MHz
  this is8.14–16.28ns, or0.88–1.76° at300kHz.

Thus a plausible design uses4BRAM36 plus distributed RAM, or5BRAM36 without
it, instead of48. These are architecture estimates only. Address/mode logic,
RAM inference, coefficient widths, timing closure, and exact latency require
RTL synthesis and implementation. The current direct lookup remains the
lowest-arithmetic, simplest-latency implementation, and is unchanged.

Reproduce with `python lut_tradeoff_analysis.py`. Detailed results are in
`lut_tradeoff.json`, `lut_tradeoff_sensors.csv`, and `lut_tradeoff_output.csv`.
