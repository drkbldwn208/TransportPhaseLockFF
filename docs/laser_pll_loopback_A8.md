# A8 DAC/ADC loopback measurement

This diagnostic build supports two physical fixtures with **the same DAC229/1 and ADC224/3**. Run `python_scripts/laser_pll_loopback.ipynb` cell by cell. The usual laser PLLs remain available when diagnostic mode is off. Firmware/helper signature is `0xA8`; keep the matching bit, HWH and all three helpers together. The prior A7 archive is preserved.

**Known intensity-servo regression (identified October 13):** the archived A8
bitstream disconnects ADC224/1 from `iq_split_0` through two orphan scalar nets,
leaving the intensity fast PI with zero input. Its mixer LO and RFDC parameters
are intact. This does not affect the loopback receiver on ADC224/3, but A8 should
not be used to operate the intensity feedback loop. The R7 RF-FRA repair removes
the orphan nets and verifies the generated and implemented signal connections.

The notebook now contains the complete startup and measurement sequence, including the user's custom `LMK_245_76_ExtRef10.txt` clock initialization and `/home/xilinx/Bitfiles/FreqLocksBranch/overlays/TransportPhaseLockFF.bit` path. It imports `laser_pll_R8` and refreshes/binds both sweep helpers to it before touching hardware. The Python ZIP includes `laser_pll_R8.py` as an exact generated copy of `laser_pll.py`. Run the notebook in order rather than substituting cells from earlier versions. Default startup initializes hardware; `initialize_hardware=False` refreshes helpers and reuses an existing `ol`, while muting the measured output. Voltage prompts use signed **mV**, converted to volts internally. The voltage model is created and passed to setup automatically. Both fixture modes save CSV/JSON/PNG under `loopback_data/`.

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

The signed DAC command is `bias + amplitude*sin(2π f t)`. Python revision 2 starts at **zero bias, 32-code peak probe and 32-code calibration step**. The older 2048/256/512-code defaults did not establish a voltage limit at the D2S output. Laser controllers must be disconnected from the driven test output.

For mixer mode, first disconnect the mixer IF and measure signed D2S voltages at codes 0 and +100, with the measured DAC mixer at 0 MHz and phase zero. The notebook provides these steps and mutes the DAC afterward. Use a high-impedance meter/scope so the initially measured unloaded voltage is conservative for a passive load. `voltage_limits(V0, V100)` calculates `offset_V=V0` and `volts_per_code=(V100-V0)/100`. Mixer `setup()` requires this measured model; it is retained on `ol` for subsequent calibration and sweep calls. Direct RF mode does not apply a D2S voltage model.

Before output writes, setup checks both zero code and the requested bias; calibration checks both bias endpoints; every probe checks its bias plus both sine peaks:

```
predicted_peak_V = abs(offset_V + volts_per_code*bias_codes)
                   + abs(volts_per_code)*amplitude_codes
predicted_peak_V + 0.020 V < 0.100 V
```

Calibration uses `step_codes` in place of amplitude. Requests outside the bound raise an exception before changing the bias or arming a probe; they are not silently clipped. Both positive and negative measured gains are supported. The notebook additionally limits initial probe/calibration excursions to at most 5 mV. It records the voltage model in the measurement JSON. Rerun setup after reloading the overlay or changing converter/LO settings; remeasure voltage after changing external gain, loading or wiring. The bound assumes a linear, stable voltage response. It is **not a hardware voltage clamp**; verify actual peaks and settling with a scope, including possible AC peaking and offset drift. The 20 mV margin is headroom, not a measured uncertainty.

The ZAD-1+ absolute maximum IF current is 40 mA and RF power is 50 mW ([manufacturer datasheet](https://www.minicircuits.com/WebStore/dashboardPdf?model=ZAD-1%2B)). For scale, 100 mV across 50 Ω corresponds to 2 mA and 0.2 mW; a diode mixer's DC IF impedance need not equal 50 Ω. A small IF waveform should be well below damaging levels with the intended source impedance. The +7 dBm LO is a separate port and is not subject to this 100 mV D2S limit. Compression and measurement bias can occur well before damage; retain the half-amplitude check.

## Updating cached Python helpers

An `AttributeError` for `fra.diagnostics` means the running sweep module is missing the A8 API. Replace **all three** Python files together from the current A8 Python archive. Reload them in dependency order and explicitly bind the modules:

```python
import importlib
import laser_pll
import laser_pll_loop_sweep as fra
import laser_pll_loopback as lb
importlib.invalidate_caches()
laser_pll = importlib.reload(laser_pll)
fra = importlib.reload(fra)
lb = importlib.reload(lb)
fra.laser_pll = laser_pll
lb.laser_pll, lb.fra = laser_pll, fra
for helper in (laser_pll, fra, lb):
    print(helper.__name__, helper.__file__)
assert lb.HELPER_REVISION >= 2
lb.check_helpers(ol)
```

No FPGA reload is needed for this Python-only update. Then rerun voltage check/setup and calibration in the updated notebook. `check_helpers()` now verifies the dependency version, functions and binding before any setup, calibration or probe writes. It does not mute an already-running output. `lb.stop(ol, mute=True)` stops the probe and disables the measured DAC command; an analog output offset can remain.

## Coherent integration

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
