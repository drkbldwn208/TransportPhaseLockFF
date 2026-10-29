# Feedforward tracking simulation

Feedforward adds the desired optical power to the controller correction **before** the shared incident-power scale and sin² inverse. It is enabled by control bit 2. It provides no advance knowledge of the shot and does not compensate propagation delay.

Comparisons use identical controller settings within each feedforward toggle. Both cases start from the same settled 8 mW state; the final integral bias differs to preserve that operating point. The mixed shot contains smooth 8–18 mW ramps, abrupt 10→15 and 15→9 mW steps, a 100 µs off interval, and restart to 12 mW. A separate smooth shot replaces the abrupt transitions with cosine ramps and ends with a smooth ramp to zero. No trace is shifted retrospectively.

| Controller | Smooth shot FF off/on RMS [mW] | Mixed shot FF off/on RMS [mW] | Mixed ramp ratio on/off | Abrupt-edge ratio on/off |
|---|---:|---:|---:|---:|
| PI | 0.30432 / 0.01758 | 1.02956 / 1.69208 | 0.068 | 1.634 |
| PI_150k_fallback | 0.11321 / 0.00745 | 0.62021 / 0.74146 | 0.070 | 1.203 |
| PII | 0.10738 / 0.00747 | 0.62133 / 0.74293 | 0.072 | 1.204 |
| PIII | 0.10703 / 0.00748 | 0.62148 / 0.74308 | 0.073 | 1.204 |

Primary whole-shot RMS uses modeled readout-band power minus desired power over the entire physical timeline, including off/restart delay. It includes no detector noise in the scoring quantity; assumed detector noise still drives the feedback loop. Separate steady, ramp, edge, clipping and calibration-range metrics are saved in JSON. A better ramp score does not imply better step overshoot or stability.

The optimizer instead scores **calibrated measured-power RMS over valid illuminated samples**. The following diagnostic uses that same sample definition, including detector noise and excluding invalid readings. Only below-range startup lasting at most 10 µs is eligible for grace, with an overall 0.1% illuminated-sample limit. Persistent range errors or any clipping disqualify optimization even if a diagnostic RMS can be calculated. These simulated flags have no DMA decimation-interval ambiguity.

| Controller | Calibrated illuminated RMS FF off/on [mW] | Optimizer usable off/on | Excluded startup fraction off/on |
|---|---:|---|---:|
| PI | 0.94419 / 1.66102 | True / False | 0.00085 / 0.00084 |
| PI_150k_fallback | 0.37622 / 0.57577 | True / True | 0.00089 / 0.00083 |
| PII | 0.37812 / 0.57785 | True / True | 0.00089 / 0.00083 |
| PIII | 0.37847 / 0.57805 | True / True | 0.00089 / 0.00083 |

## Robustness cases

| Controller | Smooth-shot FF ratio at −5% / 0 / +5% scale error | Mixed-shot ratio at −5% / 0 / +5% | With assumed 5 µW noise: mixed ratio | Maximum rail fraction across cases |
|---|---|---|---:|---:|
| PI | 0.075 / 0.058 / 0.544 | 1.379 / 1.643 / 1.077 | 1.644 | 0.0787 |
| PI_150k_fallback | 0.081 / 0.066 / 0.084 | 1.152 / 1.196 / 1.241 | 1.196 | 0.0000 |
| PII | 0.084 / 0.070 / 0.088 | 1.152 / 1.196 / 1.242 | 1.196 | 0.0000 |
| PIII | 0.085 / 0.070 / 0.088 | 1.152 / 1.196 / 1.242 | 1.196 | 0.0000 |

The 300 kHz PI at +5% scale error rails with both feedforward choices in both waveforms. Its ratios describe finite-duration nonlinear transients, not a usable improvement or a stable operating point.

With the assumed detector noise, the 150 kHz PI's steady modeled power noise is 3.077 µW RMS without FF and 3.084 µW with FF. Thus feedforward improves commanded-ramp tracking here without suppressing or appreciably adding steady detector-driven noise.

Feedforward changes the reference response, not the small-signal feedback characteristic equation at fixed operating power. It can excite a weakly damped loop more strongly. The 300 kHz PI preset has only about 0.17 dB modeled gain margin, so a +5% optical-scale error can change stability. The 150 kHz fallback, PII and PIII have about 5 dB modeled gain margin. Growing oscillations, range failures or sustained clipping invalidate a linear-performance interpretation.

## Physical assumptions and limits

- Plant impulse response: positive causal Gaussian, mean 1.131891 µs; magnitude exp[−(f/1.925351 MHz)²]. Its centroid already includes the measured 1.087 µs delay plus 44.759 ns new processing; no additional smoothing delay is added. The kernel is truncated at ±5 sigma and normalized to unity DC.
- The FRA includes the receiver/filter. Its combined delay cannot distinguish earlier actual optical power from subsequent sensing delay. The simulated waveform is the effective readout-band power; a separate optical timing measurement is needed to infer the physical field earlier in the chain.
- AOM: P=A_eff sin²(alpha u), with fitted alpha and its inverse. Estimated A_eff=184.015 mW comes from the FRA operating point; actual A_eff is varied by ±5%. Bright targets of 8–18 mW keep nominal commands above 4000. The final smooth ramp to zero traverses lower commands where the AOM fit is less reliable; its final optical tail is a model extrapolation, not a validated low-power calibration. Maximum command 21335 is within the measured upper range.
- Common optical units are 200 mW/65536. Desired power, sensed power, inverse fraction and DAC command are quantized. Sensor output is clipped to the measured low-mode calibration interval; excursions are reported rather than silently treated as valid. Zero target resets all integrators and commands zero.
- PI/PII/PIII use cascaded PI factors with the quantized preset gains. Numerical integral states use directional antiwindup and ±400 mW state/output limits. Pipeline delay is aggregated into the plant. The exact RTL side-path timing and saturation sample ordering are approximated; separate bit-exact tests establish digital arithmetic and latency.
- Added detector noise is explicitly assumed: 5 µW RMS with first-order 1 MHz bandwidth. It is not a measurement of this instrument. The same realization is used for each FF comparison. The other cases have quantization but no random detector noise.
- The inverse has the same fitted sin² shape as the plant; the ±5% scale cases test calibration normalization error, not arbitrary shape error or extra RF resonances. Large-modulation source FRA data must be checked using a smaller perturbation. Dynamics above the measured 1 MHz band are an extrapolation.
- The 1.1 ms mixed shot does not establish the long-term benefit of the 100 Hz PIII factor. Slow drift, run-to-run gain adaptation and preset switching are outside this simulation.

The smooth-to-zero shot deliberately enters the uncalibrated sensor floor before becoming exactly zero. Its optimizer qualification is therefore false, as it should be; the reported smooth-shot RMS is a model prediction, not an assertion that the hardware optimizer would accept that record. Extend the low-power calibration or use a defined final off transition for a qualified experimental score.

## Numerical check

Main timestep 4.069010 ns; all nominal mixed-shot cases repeated at half timestep. Largest change in whole-shot RMS: 0.390%. Largest waveform RMS difference: 0.010533 mW. Quantization changes individual sample sequences, so waveform differences need not decrease monotonically.

Run `python tracking_simulation.py` here to regenerate the compact JSON, plot and descriptor. It reads adjacent fitted-model/preset files and never accesses hardware. NumPy, SciPy and Matplotlib are required; Numba is optional acceleration. High-rate arrays are not exported.
