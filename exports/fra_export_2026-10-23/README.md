# Latest laser-loop FRA, loopback measurements, and discriminator model

Export updated October 23, 2026. Includes the latest closed-loop sweep, the most recent available direct/mixer loopbacks (including their individual blocks), an explicitly idealized phase-discriminator model, and a recent closed-loop phase-noise PSD with integrated noise metrics. Earlier loop sweeps and gain-extrapolation curves are excluded. Original CSV bytes and filenames are preserved; source files remain in the project.

## Summary for the receiving chat

We were measuring an optical-laser feedback loop to understand its limited bandwidth and ringing. A ZCU216 FPGA derives an error from an optical beat on ADC224/3, and DAC229/1 drives a differential-to-single-ended (D2S) stage feeding both slow piezo and fast intracavity EOM analog controllers. The EOM controller is a FALC. The measured return ratio includes both branches, the laser, converters, receiver, and active phase discriminator.

The **latest closed-loop measurement**, `laser_loop_20261014_053953.csv`, used **4× tracking gain (/40 effective phase scaling), stage 4, IIR bypassed**. It gives a main crossover of **44.73 kHz**, phase **−157.53°**, local phase margin **22.47°**, and a sampled sensitivity peak of **+8.75 dB at 46.63 kHz**. This supports poor damping near crossover. Exact controller transfer functions and EOM tuning in MHz/V remain unknown.

The most recent available direct-RF and D2S/mixer loopbacks give approximately **189.02 ns** and **194.28 ns** delay. Their saved plots identify a **90 MHz carrier**. These are amplitude-envelope tests through post-FIR I/Q, not measured phase-detector responses. Assuming their delay applies to a small phase perturbation, adding the missing stage-4 phase processing gives **250.05 ns** and **255.32 ns** for an ideal gain-plus-delay electronics model. Carrier dependence, reset-dependent converter alignment, fixtures, and AM/PM differences remain unverified systematic effects.

Suggested next-chat task: interpret the latest measured loop return ratio, use the supplied ideal discriminator model to separate likely controller/laser dynamics from electronics delay, and suggest measurements or filter changes that improve damping. Preserve the reliability flags and distinguish measured loopback response from modeled phase response.

The added phase-noise data give **0.0768 rad RMS over 1–10 kHz** and **1.341 rad RMS over 1 kHz–1 MHz**. These are a separate **8× tracking-gain acquisition with FRA off**; the transfer-function sweep above used **4×**. They provide a recent achieved-noise figure of merit, not a same-operating-point validation of the FRA/model.

## 1. Latest closed-loop measurement

**Path:** optical beat → ADC224/3 → fabric NCO/mixer/FIR → CORDIC → unwrapped phase/tracking gain → optional IIR (bypassed here) → sine injection → DAC229/1 → D2S → piezo and EOM controllers → laser → optical beat.

Two lock-ins simultaneously observe error `E` before injection and total DAC command `U` after injection. They are peak-amplitude complex phasors in DAC codes. The negative-feedback convention is `E = -L U`:

```text
D = U - E                  measured injected sine, DAC codes peak
L = -E/U                   full return ratio, dimensionless
S = U/D = 1/(1+L)          sensitivity, dimensionless
T = -E/D = L/(1+L)         complementary sensitivity, dimensionless
```

Phasors are averaged before division. Probe polarity alternates between repeats; saved phasors are already normalized to positive injection. A delay gives negative phase. These are neither raw time-domain I/Q nor noise PSDs.

Recorded settings: 32 DAC codes peak injection, 61 modulation frequencies from approximately 20 Hz to 1 MHz, 0.200–0.794 s integration per block, 4–12 accepted blocks per point. The fabric clock is 245.76 MHz. Synchronous demodulation precedes accumulation, so long averaging does not filter the live feedback path. For a calibrated 2 Vpp command span, the probe is nominally 0.977 mV peak; no independent voltage calibration accompanies this file.

The saved tracking coefficient is 419432, four times the baseline 104858. This changes detector slope, not temporal averaging. The user reported unchanged analog settings during this acquisition series. The CSV does not save the RF reference frequency or full FALC settings.

There are **28 reliable rows**; the first is approximately **5.36 kHz**. At low frequency, high feedback gain can suppress U below its uncertainty, making `-E/U` unreliable. Do not fit or unwrap phase through those rows. The reported crossover uses reliable samples in 4–100 kHz, logarithmic-frequency interpolation at the downward 0 dB crossing, and a continuous local phase branch near −180°. The reported peak is sampled, not a fitted maximum.

All retained rows have `clipped=False`, but **38 clipped attempted blocks were rejected**. Counters sum all attempts, including rejected blocks, so nonzero clip counts do not mean the retained phasor was clipped. Rejection can select quieter intervals. The closed-loop per-block file was not supplied, preventing re-analysis of those attempts. Local phase margin is not a global Nyquist-stability proof. A second probe amplitude would test linearity.

## 2. Direct and mixer loopbacks

| File prefix | Physical path | Observation |
|---|---|---|
| `loopback_rf_20261013_194213_316127` | DAC229/1 RF output → cable/attenuation → ADC224/3 | Post-mixer/FIR I/Q response to amplitude modulation |
| `loopback_mixer_20261013_192701_849567` | DAC229/1 near-DC → D2S → ZAD-1+ IF; mixer RF → ADC224/3 | Same I/Q observation |

The mixer LO was DAC228/1, PYNQ `rfdc.dac_tiles[0].blocks[1]`, amplitude GPIO `axi_gpio_12`. Both saved plot titles say 90 MHz. The intensity receiver ADC224/1 was not the final loopback ADC. The measurement design retained ADC real sampling at 1.96608 GS/s with RFDC decimation ×1, and DAC sampling at 6.88128 GS/s with interpolation ×4.

Each mode contains 61 points from approximately 10 Hz to 1 MHz, with eight blocks per point and at least one second integration per block. All aggregate points pass the saved reliability test; the 488 blocks per fixture are included. The settings/calibration JSON was not uploaded, so BLP installation, cable lengths, actual converter register snapshots and calibration vector are unavailable.

A low–high–low bias calibration defines a real vector `(gI,gQ)` in received ADC counts per DAC code. For complex demodulated I/Q amplitudes and positive probe amplitude `a`:

```text
H_parallel      = ( gI*Ihat + gQ*Qhat) / [a*(gI²+gQ²)]
H_perpendicular = (-gQ*Ihat + gI*Qhat) / [a*(gI²+gQ²)]
```

The saved `h_real/h_imag` represent H_parallel. The perpendicular response is an orthogonal modulation observation, not a phase-noise PSD. The direct response starts around 1.46 and the mixer response around 0.98: retain those values. Missing calibration metadata prevents establishing an absolute voltage gain from this normalization.

Fit `arg(H) = phase_intercept - 2*pi*f*tau` over 10 kHz–1 MHz, with weights from `complex_sem/abs(H)` and a free intercept:

| Fixture | Fitted delay | RMS phase-fit residual |
|---|---:|---:|
| Direct RF | 189.02 ns | 0.013° |
| D2S/mixer | 194.28 ns | 0.055° |

These include DAC formatting/conversion, the physical fixture, ADC conversion/packing, and the receive mixer/FIR. Long lock-in averaging adds no physical propagation delay. The ~5.3 ns difference cannot be assigned solely to the D2S board: mixer and cable differences remain. The user required less than 100 mV at the mixer IF during acquisition; the code amplitudes alone do not verify that voltage without its calibration.

## 3. Ideal phase-discriminator model for this 4× setting

### Gain and sign

Define `phi` as beat phase minus NCO reference phase, in radians, at the primary zone-1 input. The saved control word is `0x400605`, with `invert=True`. RTL first forms reference-minus-measured phase and then applies that inversion, giving a positive small-signal slope from phi to the digital error E. A separate analog inversion must be represented separately.

The 18-bit CORDIC uses `2**18` phase codes/turn. Stage 4 multiplies phase-code deviation by `tracking_coefficient / 2**26`. Therefore:

```text
K_phi = 419432 * (2**18 / (2*pi)) / 2**26
      = 419432 / (256 * 2*pi)
      = 260.76045348 DAC codes/rad
```

This is approximately `65536/(40*2*pi)`. The small difference is fixed-point coefficient rounding. At a calibrated 2 Vpp full command span, `volts_per_code=2/65536` and `K_phi=0.00795778 V/rad`. That voltage gain is conditional on actual output span, gain, loading, and sign; **do not multiply by the loopback's arbitrary low-frequency normalization** to calibrate it.

### Delay accounting

The loopback already contains the receiver through registered I/Q. Only the processing from this tap to the pre-injection error is missing:

| Operation after post-FIR I/Q | Clocks at 245.76 MHz | Delay |
|---|---:|---:|
| CORDIC half-plane rotation and vectoring | 7 | 28.483 ns |
| Phase subtraction / error register | 1 | 4.069 ns |
| Stage-4 phase register, origin subtraction, bound, multiply, round and bias/clip | 6 | 24.414 ns |
| Acquisition handoff/output selection | 1 | 4.069 ns |
| **Total extra** | **15** | **61.035 ns** |

Pipeline cross-check: raw ADC word at edge n gives post-FIR I/Q at n+7, CORDIC phase at n+14, error at n+15, tracking target at n+21, handoff at n+22, DAC word at n+23 and RFDC acceptance at n+24. Thus the missing interval is n+7 to n+22. DAC formatting and acceptance are already in the loopback. The FIR's 7.884 ns group delay is also already included. **Do not add the entire 105.540 ns stage-4 digital delay to the loopback fit.** That would count these shared stages twice.

For an ideal flat, linear phase detector, fixed tracking gain, valid I/Q, no saturation and bypassed IIR:

```text
H_post_IQ(f) = K_phi * exp(-j*2*pi*f*61.03515625e-9)

H_electronics_direct(f) = K_phi * exp(-j*2*pi*f*250.05384692e-9)
H_electronics_mixer(f)  = K_phi * exp(-j*2*pi*f*255.31797197e-9)
```

All responses are in DAC codes/rad; f is in Hz. `H_post_IQ` covers only the extra phase-processing section. The other two combine that section with the corresponding fitted loopback delay as a model of the electronics contribution around the loop. **Choose one total model; do not multiply the two fixtures or multiply H_post_IQ into a total model again.** The mixer model includes its test-fixture delay and is not an independently measured delay of the live optical feedback path.

At the measured 44.73 kHz crossover these total delays contribute approximately **−4.03°** or **−4.11°**, far less than the measured −157.53° loop phase. Substantial phase therefore remains in the controllers, frequency-to-phase conversion, laser/actuator dynamics, and any unmodeled response.

These are model estimates, not measured phase-discriminator FRA curves. Applying a 90 MHz amplitude-envelope delay to a phase detector near the optical beat carrier assumes sufficiently flat sideband response, comparable RFDC alignment, and relevant fixture delays. Fit residuals quantify local phase-line scatter, not this systematic uncertainty. No raw-phase/RF-PM transfer CSV was found in the source folder.

If the physical plant is expressed as laser **frequency** response in Hz per DAC code, insert frequency-to-phase conversion **once**: `Phi(f)=DeltaNu(f)/(j*f)` for f in Hz. It is not an extra integrator intrinsic to the stage-4 phase detector. With Phi defined at the post-FIR I/Q tap, `H_post_IQ=E/Phi` and `P=Phi/U` give `L=-H_post_IQ*P`, hence `P=-L/H_post_IQ`. That P still includes the converters and receiver front end. Dividing by the total electronics model instead gives an **effective residual plant** with the modeled converter/front-end delays removed; it is not the directly measured Phi/U, and it does not isolate an individual actuator or branch. Keep these boundaries and signs consistent.

The model equations and callable functions are in `discriminator_model.py`; fitted parameters and assumptions are in `results/discriminator_model.json`. Source audit: project `docs/laser_pll.md` (Register pipeline), `docs/laser_pll_loopback_A8.md` (Pipeline and timing reference), and `laser_pll_error.sv` / `laser_pll_tracking.sv`. No RTL was changed for this export.

## 4. Data format

All source CSVs have one header row. Phasors are peak amplitudes. Real and imaginary parts are separate columns; Boolean flags are `True`/`False`. Use actual `frequency_hz` for analysis.

### Closed-loop CSV

| Column(s) | Meaning / units |
|---|---|
| `requested_hz`, `frequency_hz` | Requested and actual modulation frequency, Hz |
| `amplitude_codes` | Positive commanded injection peak, DAC codes |
| `repeats`, `attempts` | Accepted and all attempted block counts |
| `allow_clipping`, `clipped`, `clipped_repeats` | Retention policy; clipping among retained blocks; count of clipped attempted blocks |
| `settle_s`, `measure_s`, `measure_clocks` | Per-block settling/integration, seconds and fabric clocks |
| `pll_control_word`, `acquisition_word` | Raw register snapshots; acquisition bit 3 selects stage 4 |
| `tracking_coefficient` | Raw slope coefficient; divide by 104858 for relative tracking gain |
| `iir_control_word` | Bit 0 enables optional IIR; zero here |
| `iir_b0_word`, `iir_b1_word`, `iir_pole_word` | Raw coefficient words; IIR bypassed here |
| `error_re/im`, `drive_re/im`, `injection_re/im` | E, U, D=U−E, respectively; DAC codes peak (actual names end `_re`, `_im`) |
| `loop_re/im`, `sensitivity_re/im` | L and S, dimensionless |
| `error_stderr_codes`, `drive_stderr_codes` | Complex repeat scatter / sqrt(accepted count), DAC codes |
| `dac_clip_samples` | DAC-adder clip count over all attempts |
| `detector_saturated_samples` | Internal saturation count over all attempts |
| `outside_clip_samples` | Clip/saturation events outside the integration interval |
| `repeat_consistent`, `reliable` | Saved repeat/injection consistency check; final repeat-count/SNR/unclipped quality flag |

The acquisition helper's default target SNR was 5; it checks `abs(D-a)<max(1.5 codes,0.05*a)`. Configured thresholds were not separately saved, so retain the saved flags rather than inventing new acceptance criteria.

### Loopback aggregate CSVs

| Column(s) | Meaning / units |
|---|---|
| `frequency_hz` | Actual modulation frequency, Hz |
| `h_real`, `h_imag` | Mean calibration-normalized H_parallel, dimensionless |
| `magnitude_db`, `phase_deg` | 20 log10(abs(H)) and principal phase in degrees |
| `complex_sem`, `snr` | Complex repeat scatter / sqrt(N); abs(H)/SEM, linear ratio |
| `repeats`, `reliable` | Block count and target-SNR acceptance |
| `perpendicular_real`, `perpendicular_imag` | Mean H_perpendicular, same normalized units |
| `integration_s`, `amplitude_codes` | Per-block integration in seconds and DAC peak codes |

### Loopback `_blocks.csv`

`frequency_hz`, zero-based `repeat`, actual `polarity`, `integration_s`, and `amplitude_codes` identify each block. `i_real/i_imag` and `q_real/q_imag` are lock-in amplitudes in ADC counts peak. `mean_i/mean_q` are DC means in ADC counts. `h_real/h_imag` are the block's projected H_parallel. **The phasors are already polarity-normalized; do not multiply by `polarity` again.** The missing calibration vector prevents independently recreating H from the I/Q phasors, but their saved H averages and SEM can be checked against the aggregate files.

## 5. Offline use and contents

Run `python analyze_export.py` with NumPy, pandas and Matplotlib installed. It recomputes the latest crossover and both loopback delays, verifies loopback averages against individual blocks, writes result/model JSON, and creates the latest-loop and phase-noise plots. `python analyze_phase_noise.py` regenerates just the phase-noise result. Neither accesses hardware.

```python
import numpy as np
import pandas as pd
from discriminator_model import electronics_response, post_iq_response

d = pd.read_csv('data/closed_loop/laser_loop_20261014_053953.csv')
E = d.error_re.to_numpy() + 1j*d.error_im.to_numpy()
U = d.drive_re.to_numpy() + 1j*d.drive_im.to_numpy()
L = -E/U
good = d.reliable.astype(str).str.lower().eq('true') & ~d.clipped.astype(str).str.lower().eq('true')

f_hz = d.frequency_hz.to_numpy()
H_codes_per_rad = electronics_response(f_hz, loopback_delay_s=189.01869066894383e-9)
H_nominal_V_per_rad = H_codes_per_rad * (2.0/65536)
# Use good points and consistent block boundaries before dividing L by a model.
```

`data/` contains six unchanged CSVs: one closed-loop file, two loopback aggregate/block pairs, and the previously calculated ten-capture phase PSD. `figures/` contains this loop's plot, both saved loopback plots, and the added phase-noise plot. `results/` contains recomputed metrics, the discriminator model, and phase-noise conditions/results. `manifest.json` records paths and SHA-256 hashes. There are no older loop transfer results or projected higher-gain curves.

## 6. Recent closed-loop phase-noise figure of merit

See **`figures/phase_noise_8x.png`**: the upper panel plots one-sided phase PSD, and the lower panel accumulates phase variance from 1 kHz to the plotted upper frequency before taking its square root. The underlying `data/phase_noise/shortest_iq_phase_psd.csv` is the previously shown spectrum from `laser_iq_FPGA_shortest_0.npz` through `_9.npz` in the project's `ILAData/10-13-IQ/` folder. The raw I/Q files are not bundled; their source names/hashes and capture conditions are recorded in `results/phase_noise_capture_conditions.json`.

Conditions: FPGA lock, **8× tracking gain**, FRA tone off, physical beat/reference both 800 MHz according to the experimental conversation. The user reported the reference laser was more stable than in the preceding batch. Each record has 262144 samples at 15.36 MS/s (monitor decimation D=4), giving 17.067 ms per record and 0.1707 s across ten separate captures. These are passive noise observations, separate from the **4×** driven FRA. Do not simply rescale this PSD to predict the 4× noise: feedback sensitivity and disturbance contributions change with gain.

Phase was extracted as `unwrap(angle(I+jQ))` at the full saved sample rate, before any further averaging. No linear drift was removed. Welch used 65536-point periodic Hann windows, 50% overlap, constant detrending per segment, and density scaling: seven overlapping segments per record, 234.375 Hz bin spacing. The CSV is the original unfiltered fast-capture analysis, not the later 2 MHz filtered PLL/FPGA comparison. No monitor-boxcar, alias, or readout-noise correction was applied.

Each spectrum is averaged in **linear rad²/Hz**, not dB. For the equal-weight mean PSD, the figure of merit is `sigma_phi = sqrt(sum(S_phi[f] * df))`, retaining bins with `low <= f < high` and including discrete peaks and broadband noise:

| Integration band | Mean-PSD phase RMS | Range of individual-capture RMS |
|---|---:|---:|
| 1–10 kHz | **0.07676 rad** (4.40°) | 0.0618–0.1069 rad |
| 10–100 kHz | 1.1419 rad | 1.0150–1.4269 rad |
| 100 kHz–1 MHz | 0.6994 rad | 0.6020–0.7903 rad |
| 1 kHz–1 MHz | **1.3412 rad** (76.85°) | 1.2452–1.5880 rad |

The combined RMS is the square root of mean variance, not the arithmetic average of per-record RMS. PSD ordinate is **10 log10(S_phi in rad²/Hz)**, not single-sideband dBc/Hz. Columns are `frequency_hz` and `capture_0_phase_rad2_per_hz` through `capture_9_phase_rad2_per_hz`; the full stored frequency axis extends to 7.68 MHz, but the figure and quoted metric use 1 kHz–1 MHz. The finite-duration/bin convention should be retained when comparing numbers.

Across these records, minimum I/Q magnitude remained at least 0.875 of the record median and maximum adjacent phase step was 0.592 rad, supporting resolved unwrapping without amplitude dropouts. Phase extraction removes direct amplitude dependence, not all readout or AM-to-PM noise. The result measures **beat-phase fluctuations**, including the reference laser and detection chain; it is not an independently measured absolute linewidth. These short records do not determine rare-slip rate or long-term stability.
