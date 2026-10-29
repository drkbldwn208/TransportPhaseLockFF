# PI feedforward and proportional setpoint weighting

This is an offline comparison; no RTL, bitstream or board settings changed. It uses the same mixed shot, fitted AOM and readout-band plant as `tracking_simulation.py`, including 44.759 ns added processing. Each case begins at the same settled 8 mW. Zero target resets the integral; restart therefore tests a separate practical condition.

The weighted controller is `u_virtual = FF*r + Kp*(beta*r-y) + I`, with `dI/dt = Ki*(r-y)` and `Ki=Kp*omega_i`. The integral always receives the full error. Consequently the disturbance-rejection denominator `1+P*(Kp+Ki/s)` is unchanged. The reference numerator becomes `P*(FF+beta*Kp+Ki/s)`.

| Controller | Case | First 10–90% rise [µs] | Step overshoot [%] | ±2% settle [µs] | Whole mixed-shot RMS [mW] |
|---|---|---:|---:|---:|---:|
| PI_150k_fallback | FF off | 0.701 | 26.8 | 6.62 | 0.62021 |
| PI_150k_fallback | FF on, beta=1 | 0.207 | 111.1 | 8.04 | 0.74146 |
| PI_150k_fallback | FF on, beta=0 | 0.252 | 78.5 | 6.64 | 0.66268 |
| PI | FF off | 0.274 | 41.6 | 111.23 | 1.02956 |
| PI | FF on, beta=1 | 0.176 | 122.5 | 133.56 | 1.69208 |
| PI | FF on, beta=0 | 0.277 | 41.0 | 111.22 | 1.02561 |

Feedforward gives a faster initial rise in this model. The worse overall error comes from the larger overshoot and ringing after arrival. Weighting the proportional reference reduces this kick, but does not eliminate it.

Rise time uses the first threshold crossings and does not imply that the power stays at its target. Overshoot is a percentage of the 5 mW step, not of the final 15 mW power. Overshoot and settling are evaluated over the entire 150 µs plateau. RMS is calculated over the unchanged 1.1 ms physical timeline, including ramps, steps, off and restart. Actual modeled optical/readout power is scored; clipping and sensor-range validity remain in JSON.

For a change of target Δr before the measured power has responded, the immediate virtual-command jump is `(FF+beta*Kp)*Δr`. Standard feedforward therefore adds to the proportional jump. Choosing beta=0 removes that proportional reference kick, but the integral continues charging while propagation delays the response. Approximately `Ki*Δr*delay` additional virtual power can accumulate during this interval, so beta=0 does not guarantee zero overshoot.

With the 150 kHz preset, Kp≈0.353: the initial step coefficients are 0.353 (no FF), 1.353 (standard FF), and 1 (weighted FF). With the 300 kHz preset, Kp≈1.008, so no FF and weighted FF have almost the same linear reference response. Weighting can change which loop modes a pulse excites; it does not improve the stability margins of those modes.

A slower desired waveform or a separate causal reference prefilter can limit excitation without reducing disturbance feedback gain. A model-following feedforward term would require a separately identified plant and an explicit choice of desired tracking dynamics; exact cancellation of an unknown pure delay cannot be causal. No such filter is implemented here.

These are nominal-model predictions, not hardware validation. Sensor noise is omitted in this extra comparison; noise and ±5% scale tests for the original controller remain in `tracking_simulation.json`. The 300 kHz setting retains its very small gain margin. Only PI is tested here; extending weighting to PII/PIII requires preserving the full cascaded integral reference dynamics.

Both beta=0 cases were rerun at half timestep. Largest whole-shot RMS change: 0.314%. The standard cases reproduce the preceding simulation's RMS to floating-point precision.

Run `python setpoint_weighting_simulation.py` in this directory to regenerate JSON, figure and this note.
