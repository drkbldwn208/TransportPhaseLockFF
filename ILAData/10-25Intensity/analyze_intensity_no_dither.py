"""Separate the intensity-loop oscillation from the 180 MHz demodulator image.

Each frame contains four consecutive I samples at 983.04 MS/s, but frames are
spaced by 2**D / 245.76 MHz. Lane phase differences therefore distinguish a
baseband tone from its high-frequency aliases. No hardware is accessed.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal import coherence, welch

folder = Path(__file__).resolve().parent
with np.load(folder / "intensity_no_dither.npz", allow_pickle=False) as saved:
    raw = saved["raw"]
    fs_hz = float(saved["sample_rate_hz"])
    metadata = json.loads(str(saved["metadata_json"]))

i_counts = raw[:, :2].copy().view(np.int16).reshape(-1, 4).astype(float)
commands = raw[:, 2].copy().view(np.int16).reshape(-1, 2).astype(float)
pi_codes, dac_codes = commands.T
assert np.array_equal(pi_codes, dac_codes), "This record is not dither-free."
lane_rate_hz = 983.04e6  # ADC 1.96608 GS/s, RFDC decimation 2.
t_s = np.arange(len(raw)) / fs_hz
window = np.hanning(len(raw))
centered_i = i_counts - i_counts.mean(axis=0)


def lane_phasors(frequency_hz):
    # Positive recorded-frequency convention: x(t) = Re[X exp(+i*2*pi*f*t)].
    weight = window * np.exp(-2j * np.pi * frequency_hz * t_s)
    return 2 * (weight @ centered_i) / window.sum()


frequency_hz, lane_psd = welch(i_counts[:, 0], fs=fs_hz, nperseg=65536)
_, mean_psd = welch(i_counts.mean(axis=1), fs=fs_hz, nperseg=65536)
_, pi_psd = welch(pi_codes, fs=fs_hz, nperseg=65536)
df_hz = frequency_hz[1] - frequency_hz[0]
peak_bin = 1 + np.argmax(pi_psd[1:])
fit = minimize_scalar(
    lambda f: -abs(lane_phasors(f)[0])**2,
    bounds=(frequency_hz[peak_bin] - df_hz, frequency_hz[peak_bin] + df_hz),
    method="bounded", options={"xatol": 1e-5})
ring_hz = float(fit.x)
image_hz = 2 * abs(metadata["lo_mixer"]["Freq"]) * 1e6
image_alias_hz = abs((image_hz + fs_hz / 2) % fs_hz - fs_hz / 2)

results = {
    "source": "intensity_no_dither.npz",
    "sample_rate_hz": fs_hz,
    "duration_s": len(raw) / fs_hz,
    "lane_sample_rate_hz": lane_rate_hz,
    "pi_zero_fraction": float(np.mean(pi_codes == 0)),
    "adc_lane_mean_counts": i_counts.mean(axis=0).tolist(),
    "adc_lane_std_counts": i_counts.std(axis=0).tolist(),
    "notes": [
        "Line power integrates a +/-10 kHz band in the Welch PSD; fractions are relative to the integrated non-DC PSD.",
        "Physical-frequency inference uses the phase slope across four adjacent ADC samples and is modulo the lane sample rate.",
        "A matching 180 MHz image does not establish that it causes the separate low-frequency loop oscillation.",
    ],
}
for label, f_hz in (("ringing", ring_hz), ("mixing_image", image_alias_hz)):
    phasors = lane_phasors(f_hz)
    phase_rad = np.unwrap(np.angle(phasors / phasors[0]))
    phase_step_rad = np.polyfit(np.arange(4), phase_rad, 1)[0]
    band = abs(frequency_hz - f_hz) < 10000
    line = {
        "recorded_frequency_hz": float(f_hz),
        "lane_phase_relative_deg": np.rad2deg(phase_rad).tolist(),
        "phase_step_deg": float(np.rad2deg(phase_step_rad)),
        "inferred_frequency_modulo_lane_rate_hz": float(phase_step_rad / (2*np.pi) * lane_rate_hz),
        "lane_peak_amplitude_counts": abs(phasors).tolist(),
    }
    for name, psd in (("raw_lane", lane_psd), ("four_lane_mean", mean_psd), ("pi_command", pi_psd)):
        variance = float(psd[band].sum() * df_hz)
        line[name] = {"line_rms_counts": variance**0.5,
                      "variance_fraction": float(psd[band].sum()/psd.sum())}
    results[label] = line
f_coh, coh = coherence(i_counts.mean(axis=1), pi_codes, fs=fs_hz, nperseg=16384)
results["ringing_adc_pi_coherence"] = float(coh[np.argmin(abs(f_coh - ring_hz))])
(folder / "intensity_no_dither_analysis.json").write_text(json.dumps(results, indent=2) + "\n")

fig = plt.figure(figsize=(12, 8), constrained_layout=True)
grid = fig.add_gridspec(2, 2)
adc_ax, pi_ax = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])
psd_ax = fig.add_subplot(grid[1, :])
zoom = t_s < 15e-6
adc_ax.plot(t_s[zoom]*1e6, i_counts[zoom, 0], color="0.75", lw=.7, label="Raw I lane 0")
adc_ax.plot(t_s[zoom]*1e6, i_counts[zoom].mean(axis=1), lw=1.1, label="Four-lane mean")
adc_ax.axhline(5000, color="k", ls=":", lw=1, label="Setpoint")
adc_ax.set(xlabel="Time [µs]", ylabel="ADC I [counts]", title="Fast excursions with the FRA tone off")
adc_ax.legend(fontsize=9)
pi_ax.plot(t_s[zoom]*1e6, pi_codes[zoom], color="tab:red", lw=1)
pi_ax.axhline(0, color="k", lw=.7)
pi_ax.set(xlabel="Time [µs]", ylabel="PI / DAC command [codes]",
          title=f"Command at zero for {100*results['pi_zero_fraction']:.1f}% of the capture")
for label, psd, color in (("Raw I lane 0", lane_psd, "0.55"),
                          ("Four-lane mean I", mean_psd, "tab:blue"),
                          ("PI / DAC command", pi_psd, "tab:red")):
    psd_ax.loglog(frequency_hz[1:]/1e6, psd[1:], label=label, color=color, lw=.9)
psd_ax.axvline(ring_hz/1e6, color="k", ls="--", lw=.8)
psd_ax.axvline(image_alias_hz/1e6, color="tab:purple", ls="--", lw=.8)
psd_ax.text(ring_hz/1e6*1.12, 2e4, f"{ring_hz/1e3:.3f} kHz\nloop oscillation", fontsize=9)
psd_ax.text(image_alias_hz/1e6*.95, 2e4, "180 MHz image\naliased to 4.32 MHz",
            ha="right", fontsize=9, color="tab:purple")
psd_ax.set(xlabel="Recorded frequency [MHz]", ylabel="One-sided PSD [counts²/Hz]",
           xlim=(.02, fs_hz/2e6), ylim=(1e-4, 2e5))
psd_ax.legend(loc="lower left", fontsize=9)
for ax in (adc_ax, pi_ax, psd_ax):
    ax.grid(True, which="both", alpha=.25)
fig.suptitle("Intensity servo: separate 391 kHz oscillation and 180 MHz mixing image")
fig.savefig(folder / "intensity_no_dither_analysis.png", dpi=180)
print(json.dumps({"ringing_hz": ring_hz,
                  "image_alias_hz": image_alias_hz,
                  "pi_zero_fraction": results["pi_zero_fraction"]}, indent=2))
