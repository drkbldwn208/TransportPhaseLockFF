"""Compare measured intensity ringing before/after the PI gain reduction.

PSD bands refer to recorded frequencies: frame selection aliases the 180 MHz
mixing image to 4.32 MHz. ADC counts are not converted to optical power here.
"""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import welch

folder = Path(__file__).resolve().parent
fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
summary = {}
for name, label, color in [
    ("intensity_no_dither.npz", "Kp=-1, Ki=-0.005", "tab:red"),
    ("intensity_no_dither (1).npz", "Kp=-0.4, Ki=-0.0015", "tab:blue"),
]:
    with np.load(folder / name, allow_pickle=False) as data:
        raw = data["raw"]
        fs_hz = float(data["sample_rate_hz"])
        status = int(data["status"])
        config = json.loads(str(data["metadata_json"]))
    i = raw[:, :2].copy().view(np.int16).reshape(-1, 4).astype(float)
    commands = raw[:, 2].copy().view(np.int16).reshape(-1, 2).astype(float)
    assert np.array_equal(commands[:, 0], commands[:, 1])
    c = commands[:, 0]
    avg = i.mean(axis=1)
    t_us = np.arange(len(raw)) / fs_hz * 1e6
    zoom = t_us < 15
    axes[0, 0].plot(t_us[zoom], avg[zoom], color=color, label=label, lw=.8)
    axes[0, 1].plot(t_us[zoom], c[zoom], color=color, label=label, lw=.8)
    f, p = welch(avg, fs=fs_hz, nperseg=65536)
    _, pc = welch(c, fs=fs_hz, nperseg=65536)
    _, p_lane = welch(i[:, 0], fs=fs_hz, nperseg=65536)
    axes[1, 0].semilogy(f/1e6, p, color=color, label=label, lw=.8)
    axes[1, 1].semilogy(f/1e6, pc, color=color, label=label, lw=.8)
    df_hz = f[1] - f[0]
    low = (f > 0) & (f < 1e6)
    image = abs(f - 4.32e6) < 10000
    summary[name] = {
        "configuration": config,
        "status_hex": hex(status),
        "duration_s": len(raw)/fs_hz,
        "welch_bin_hz": float(df_hz),
        "pi_mean_codes": float(c.mean()),
        "pi_range_codes": [float(c.min()), float(c.max())],
        "pi_zero_fraction": float(np.mean(c == 0)),
        "pi_std_codes": float(c.std()),
        "adc_mean_counts": float(i.mean()),
        "raw_lane_std_counts": i.std(axis=0).tolist(),
        "raw_adc_outside_table_fraction": float(np.mean((i < 500) | (i > 9500))),
        "mean_adc_recorded_below_1MHz_rms_counts": float(np.sqrt(p[low].sum()*df_hz)),
        "pi_recorded_below_1MHz_rms_codes": float(np.sqrt(pc[low].sum()*df_hz)),
        "pi_image_band_rms_codes": float(np.sqrt(pc[image].sum()*df_hz)),
        "raw_lane_image_variance_fraction": float(p_lane[image].sum()/p_lane.sum()),
    }

axes[0, 0].set(xlabel="Time [µs]", ylabel="Four-lane mean ADC I [counts]",
               title="The large intensity-readout oscillation disappears")
axes[0, 0].axhline(5000, color="k", ls=":", lw=.8)
axes[0, 1].set(xlabel="Time [µs]", ylabel="PI / DAC command [codes]",
               title="New command remains away from zero")
axes[0, 1].axhline(0, color="k", ls=":", lw=.8)
axes[1, 0].set(xlabel="Recorded frequency [MHz]", ylabel="ADC PSD [counts²/Hz]",
               xlim=(.02, 1), ylim=(1e-5, 1e5), title="Recorded band below 1 MHz")
axes[1, 0].axvline(.391185, color="k", ls=":", lw=.8)
axes[1, 1].set(xlabel="Recorded frequency [MHz]", ylabel="PI command PSD [codes²/Hz]",
               xlim=(.02, 7.68), ylim=(1e-5, 1e5), title="Remaining 4.32 MHz line is the 180 MHz image")
axes[1, 1].axvline(4.32, color="k", ls=":", lw=.8)
for ax in axes.flat:
    ax.grid(True, which="both", alpha=.25)
    ax.legend(fontsize=8)
fig.suptitle("Intensity servo: reduced gains remove the 391 kHz limit cycle")
fig.savefig(folder / "intensity_gain_comparison.png", dpi=170)
(folder / "intensity_gain_comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
print("Saved intensity_gain_comparison.png and intensity_gain_comparison.json")
