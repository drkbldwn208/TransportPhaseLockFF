# A8 DAC/ADC loopback measurement

This diagnostic build supports two physical fixtures with **the same DAC229/1 and ADC224/3**. Run `python_scripts/laser_pll_loopback.ipynb` cell by cell. The usual laser PLLs remain available when diagnostic mode is off. Firmware/helper signature is `0xA8`; keep the matching bit, HWH and all three helpers together. The prior A7 archive is preserved.

## Connections and converter settings

| Mode | Physical signal path | Measured DAC mixer | Receive reference |
|---|---|---|---|
| `rf` | DAC229/1 → RF cable/attenuation → ADC224/3 | C2R at carrier frequency | Fabric NCO at carrier frequency |
| `mixer` | DAC229/1 → D2S → optional BLP → ZAD-1+ IF; mixer RF → ADC224/3 | C2R at 0 MHz, phase reset to zero | Fabric NCO at TP LO frequency |

Mixer LO: **DAC228/1**, PYNQ `rfdc.dac_tiles[0].blocks[1]`, amplitude `ol.axi_gpio_12.channel1`, using the user's existing TP LO. The intensity ADC224/1/fast-PI path is not part of this measurement. Move the mixer RF cable to ADC224/3. DAC229/3 and the second PLL are not repurposed.

Start both modes at 90 MHz so their converter/receiver contributions can be compared. Direct RF can also use 800 MHz to test the normal beat-note operating frequency. ZAD-1+ RF/LO coverage is 0.5–500 MHz, IF DC–500 MHz and its nominal LO is +7 dBm ([Mini-Circuits datasheet](https://www.minicircuits.com/pdfs/ZAD-1%2B.pdf)). A DAC amplitude fraction does not establish connector power. Check LO power and the linearity of the IF/D2S path. At 90 MHz the existing broad PLL FIR leaves an image near 65.76 MHz after decimation; coherent demodulation/integration rejects this distant image for the 10 Hz–5 MHz sweep. This is not a claim that the normal atan2 phase detector has its 800 MHz image performance at 90 MHz.

RFDC ADC remains raw real, ×1 decimation, 1.96608 GS/s, eight samples per 245.76 MHz beat. DAC remains 6.88128 GS/s, ×4 interpolation, seven repeated complex pairs per beat. Only the measured DAC NCO and fabric reference are set by diagnostic setup. No ADC RFDC settings or sample clocks change. TP LO is set by the explicit notebook cell; `setup()` itself only reads it.

For the D2S/BLP test, the mixer IF provides a nominal 50 Ω load. This differs from a tee containing only high-impedance controller/scope inputs. Record which load and cables are present; the 50 Ω source resistor alone does not terminate the far end of the filter/cable.

## Measurement and averaging

The signed DAC command is `bias + amplitude*sin(2π f t)`. Suggested starting values are bias 2048 and amplitude 256 codes: nominal +62.5 mV bias and 7.81 mV peak for a calibrated 2 Vpp full-scale span. Actual connector voltage depends on termination and D2S gain. Laser controllers must be disconnected from the driven test output.

The two existing HLS lock-ins observe post-mixer/FIR I and Q instead of scaled error and drive. Their references remain synchronized with the digital DAC command. They multiply at 245.76 MHz and accumulate into signed 72-bit results. Thus **demodulation precedes averaging/decimation**; a MHz response is not discarded by a slow pre-demodulator low-pass.

Default integration is at least one second and an integer number of quantized DDS cycles. The frequency step is 0.457763672 Hz; actual frequency is saved. Eight complex blocks per point are averaged, extended to 24 if repeat SNR is below 30. Probe polarity alternates; the helper normalizes its sign. A one-second rectangular integration has approximately 0.5 Hz one-sided equivalent noise bandwidth per demodulated quadrature. Independent repeats reduce noise as √N. Drift, compression, leakage synchronous with the probe and fixture resonances do not disappear through averaging. Every block is saved separately, and low-SNR points remain flagged.

The old closed-loop FRA still uses E/U and its existing helper. This loopback measures a feed-forward hardware response; do not apply `L=-E/U` to I/Q data.

## Calibration and units

The FIR has eight fractional bits. The diagnostic probe shifts right by six, preserving **two fractional ADC-count bits** in the 20-bit HLS input. Results and means divide by four in Python. There is no dependence on phase gain, the /160 mapping, CORDIC validity or capture stage.

A low–high–low DC-bias calibration measures a real response vector `g=(gI,gQ)` in post-mixer ADC counts per DAC code. Subtracting two bias levels removes fixed mixer LO leakage and receiver offsets. Repeating the low level detects drift; the helper rejects changes larger than 5% of the calibration step response. This is a stability check, not proof of analog linearity.

With measured peak phasors Î and Q̂ and positive DAC probe amplitude a:

```
H_parallel = (gI*Î + gQ*Q̂) / (a*(gI²+gQ²))
H_perpendicular = (-gQ*Î + gI*Q̂) / (a*(gI²+gQ²))
```

`H_parallel(0)=1` by calibration, including physical polarity. Unknown constant carrier phase cancels. `H_perpendicular` monitors an orthogonal modulation component; it need not vanish for unequal RF sidebands or AM-to-PM conversion. Recalibrate after resetting converters/NCOs, changing fixture or carrier. Compare pre/post calibration and half-amplitude sweeps.

The helper saves `loopback_MODE_TIMESTAMP.csv`, `_blocks.csv`, `.json` metadata and `.png` plots under notebook-relative `loopback_data/`. Mean/phasor units are ADC counts, not calibrated input volts. No PSD or raw DMA file is implied by these measurements.

## Pipeline and timing reference

No feedback registers are added. DAC command/reference alignment, the original one-register DAC formatter, RFDC settings, mixer and FIR are retained. The only additions are a diagnostic probe multiplexer, raw-ADC rail detector, DC accumulators and two read-only GPIOs.

| Operation | Relation to the measured phase |
|---|---|
| HLS tone/reference join | Same transaction paired before injection |
| Three stimulus registers | Tone, envelope product, injection; sine/cosine reference delayed identically |
| Digital injection point | Time origin of the reported transfer response |
| Existing DAC formatter and RFDC acceptance | Inside the measured path |
| DAC interpolation/conversion, fixture, ADC conversion/packing | Inside the measured path; not inferred from RTL timing |
| Existing ADC mixer/FIR | Final I/Q registered at n+7 relative to raw ADC word edge n; FIR signal group delay also 7.884 ns |
| Probe and reference register/HLS pipeline | Common observation transport, not extra delay falsely assigned to the physical return |
| Long lock-in integration | Narrows measurement noise bandwidth; does not delay the feedback path |

Fit unwrapped phase with a free intercept, `phase(f)=phi0−2π f tau`. Phase curvature indicates dispersion; a single fitted tau depends on fit band. The helper does not automatically subtract digital delays. Do not subtract the full 90–105 ns PLL error latency: CORDIC, unwrapping, phase scaling and IIR are not in this measurement. Absolute DAC and ADC delays cannot be separated by this one experiment. Repeat after resets to assess repeatability; ADC/DAC startup synchronization can affect latency ([AMD RFDC synchronization guidance](https://docs.amd.com/r/en-US/pg269-rf-data-converter/Deterministic-Multi-Tile-Synchronization-API-Use)).

Divide mixer-fixture H by direct-fixture H at the **same carrier and modulation frequencies** to remove shared contributions. Different RF cable lengths, mixer conversion response, and any difference between the DAC analog response near DC and near the RF carrier remain in that ratio. Validate the delay measurement by inserting known extra cable.

## RTL and registers

`pll_fra` control bit 0 arms a measurement; new bit 1 selects I/Q observations and is latched at arm. Clearing arm ramps down the stimulus while preserving the selection until completion. With bit 1 clear, existing closed-loop FRA behavior remains unchanged.

`pll_loopback_i` at `0xA0300000` and `pll_loopback_q` at `0xA0310000` are read-only GPIOs. Offset 0 contains the low 32 bits; offset 8 the high 32 bits of a sign-extended 52-bit sum. Sums reset on arm, integrate over exactly the same window as lock-in products, and hold after completion. Read only after DONE. Divide by `4*measured_samples` to get mean ADC counts. The second PLL has the probe selector internally but these mean GPIOs are connected to the primary pair; the loopback helper deliberately targets `ol`, not `channel(ol,1)`.

DAC clipping counts retain their meaning. In I/Q mode the second saturation counter records raw ADC beats with any lane within 16 codes of a rail. It does not claim to detect analog compression before the ADC. Measurement-window flags, outside-window counts, sample-loss/DAC-stall/generator-gap/abort checks remain active. A missing CORDIC phase does not veto a valid I/Q measurement. DC DAC mode still requires global output enable.

See [RTL source walkthrough](laser_pll_rtl_walkthrough.md) for grouped line descriptions. Simulations use the actual HLS generator/demodulator RTL, recover a known four-clock gain/delay, check signed DC means and missing I/Q faults, and rerun the full PLL arithmetic/packing regression. Python checks exercise 403 ns delay recovery, leakage-subtracted calibration, amplitude/sign normalization, cleanup and saved data. Full routed timing and hardware-package status are recorded in the release verification JSON; simulations are not measurements on the board.
