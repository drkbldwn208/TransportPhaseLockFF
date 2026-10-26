"""Plot measured closed-loop beat-phase PSD and integrate band-limited variance.

The input CSV contains one-sided Welch spectra from ten 15.36 MS/s I/Q
records at 8x FPGA tracking gain, FRA off. Average PSDs in linear units,
then integrate over frequency and take the square root. This is a separate
operating point from the 4x FRA; it cannot validate that sweep quantitatively.
Raw-I/Q processing is documented in README; this script uses the saved PSDs.
"""
from pathlib import Path
import json
import os
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent


def analyze_phase_noise():
    source = ROOT/"data/phase_noise/shortest_iq_phase_psd.csv"
    data = pd.read_csv(source)
    frequency_hz = data.frequency_hz.to_numpy()
    columns = [f"capture_{n}_phase_rad2_per_hz" for n in range(10)]
    per_record = data[columns].to_numpy()
    df_hz = frequency_hz[1]-frequency_hz[0]
    assert np.allclose(np.diff(frequency_hz), df_hz)
    assert np.isclose(df_hz, 234.375)
    assert np.all(np.isfinite(per_record)) and np.all(per_record >= 0)
    mean_psd = per_record.mean(axis=1)  # Equal capture weights, never average dB.
    rows = []
    for low_hz, high_hz in ((1e3, 1e4), (1e4, 1e5), (1e5, 1e6), (1e3, 1e6)):
        band = (frequency_hz >= low_hz) & (frequency_hz < high_hz)
        variances_rad2 = per_record[band].sum(axis=0)*df_hz
        variance_rad2 = mean_psd[band].sum()*df_hz
        assert np.isclose(variance_rad2, variances_rad2.mean())
        rows.append(dict(band_hz=[low_hz, high_hz],
            phase_variance_rad2=float(variance_rad2),
            phase_rms_rad=float(np.sqrt(variance_rad2)),
            phase_rms_deg=float(np.rad2deg(np.sqrt(variance_rad2))),
            per_capture_rms_range_rad=[float(np.sqrt(variances_rad2.min())),
                                       float(np.sqrt(variances_rad2.max()))]))
    assert np.isclose(sum(row["phase_variance_rad2"] for row in rows[:3]),
                      rows[3]["phase_variance_rad2"])
    report = dict(source=str(source.relative_to(ROOT)),
        tracking_gain_relative_to_stage3=8, fra_tone_on=False,
        sample_rate_hz=15.36e6, samples_per_capture=262144, captures=10,
        duration_per_capture_s=262144/15.36e6, fft_length=65536,
        fft_overlap_samples=32768, fft_bin_hz=float(df_hz),
        window="periodic Hann", detrending="constant per segment; no linear drift removal",
        spectrum_units="one-sided rad^2/Hz", bands=rows,
        integration="sum PSD*df for low <= f < high; includes lines and broadband noise",
        limitations=["8x noise acquisition is not matched to the exported 4x FRA.",
                     "Measured beat includes both lasers and detection noise; not absolute laser noise.",
                     "No detector noise-floor, monitor boxcar or alias correction applied.",
                     "Short captures do not establish rare-slip rate or long-term stability.",
                     "Phase extraction suppresses direct AM dependence but not every AM-to-PM effect."])
    (ROOT/"results").mkdir(exist_ok=True)
    (ROOT/"results/phase_noise_summary.json").write_text(json.dumps(report, indent=2)+"\n")

    os.environ.setdefault("MPLCONFIGDIR", "/tmp/fra_export_mpl")
    os.environ.setdefault("XDG_CACHE_HOME", "/tmp/fra_export_cache")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    band = (frequency_hz >= 1e3) & (frequency_hz < 1e6)
    f = frequency_hz[band]
    cumulative_rms = np.sqrt(np.cumsum(mean_psd[band])*df_hz)
    assert np.isclose(cumulative_rms[-1], rows[-1]["phase_rms_rad"])
    fig, axes = plt.subplots(2, 1, figsize=(10, 7.8), sharex=True, layout="constrained")
    for n in range(10):
        axes[0].semilogx(f, 10*np.log10(per_record[band, n]), color=".72", lw=.55,
                        alpha=.65, label="Individual captures" if n == 0 else None)
    axes[0].semilogx(f, 10*np.log10(mean_psd[band]), color="#1769aa", lw=1.2,
                    label="Mean PSD (linear average)")
    axes[0].set(ylabel="One-sided phase PSD (dB rad²/Hz)",
                title="Measured beat phase; prominent features around 65, 86 and 175 kHz")
    axes[0].legend(fontsize=9)
    axes[1].semilogx(f, cumulative_rms, color="#1769aa", lw=1.5)
    axes[1].set(xlabel="Fourier frequency / integration upper limit (Hz)",
                ylabel="Integrated phase noise (rad RMS)", xlim=(1e3, 1e6), ylim=(0, 1.5),
                title="Cumulative variance integrated from 1 kHz, then square root")
    axes[1].text(.04, .95,
        f"1–10 kHz: {rows[0]['phase_rms_rad']:.4f} rad RMS\n"
        f"1 kHz–1 MHz: {rows[-1]['phase_rms_rad']:.3f} rad RMS",
        transform=axes[1].transAxes, va="top", fontsize=11,
        bbox=dict(facecolor="white", edgecolor=".8", alpha=.95))
    for ax in axes:
        ax.grid(alpha=.2, which="both")
        for edge in (1e4, 1e5): ax.axvline(edge, color=".5", ls=":", lw=.8)
    fig.suptitle("Recent FPGA closed-loop phase noise: 8× tracking gain, FRA tone OFF\n"
                 "Ten 17.07 ms captures at 15.36 MS/s; 234.375 Hz PSD bins", fontsize=12)
    fig.supxlabel("Different operating point from the exported 4× transfer-function sweep.\n"
                  "Beat measurement includes reference-laser and readout noise; no floor subtraction.", fontsize=9)
    (ROOT/"figures").mkdir(exist_ok=True)
    fig.savefig(ROOT/"figures/phase_noise_8x.png", dpi=160)
    plt.close(fig)
    return report


if __name__ == "__main__":
    print(json.dumps(analyze_phase_noise(), indent=2))
