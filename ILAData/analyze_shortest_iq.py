"""Measure resolved phase motion in the ten D=4 I/Q captures.

User reports 8x tracking gain and FRA off, with a more stable reference laser.
Phase is unwrapped at 15.36 MS/s before any further averaging. No linear drift
is removed. Welch uses constant detrending per segment; band powers include
discrete lines and the continuous background. Separate records are not joined.
"""
from pathlib import Path
import hashlib
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/shortest_iq_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks, welch

DIRECTORY = Path(__file__).resolve().parent / "10-13-IQ"
BANDS_HZ = ((1000, 10000), (10000, 100000), (100000, 1000000), (1000000, 7680000))


def read_record(number):
    path = DIRECTORY / f"laser_iq_FPGA_shortest_{number}.npz"
    with np.load(path, allow_pickle=False) as data:
        z = data["i_adc_counts"] + 1j*data["q_adc_counts"]
        fs_hz = float(data["sample_rate_hz"])
        assert int(data["decimation_log2"]) == 4 and fs_hz == 15360000
    magnitude = abs(z)
    assert np.isfinite(z).all() and magnitude.min() > 0
    phase_rad = np.unwrap(np.angle(z))
    phase_rad -= phase_rad[0]
    steps_rad = np.angle(z[1:]*z[:-1].conj())
    assert np.allclose(np.diff(phase_rad), steps_rad, atol=1e-10)
    # These are empirical checks of this data, not a general unwrap guarantee.
    assert max(abs(steps_rad)) < .6 and magnitude.min()/np.median(magnitude) > .85
    f_hz, phase_psd = welch(phase_rad, fs_hz, nperseg=65536, noverlap=32768,
                            detrend="constant", scaling="density")
    _, amplitude_psd = welch(magnitude/magnitude.mean(), fs_hz, nperseg=65536,
                            noverlap=32768, detrend="constant", scaling="density")
    df_hz = f_hz[1]-f_hz[0]
    band_rms = {f"{lo:g}_{hi:g}_hz": float(np.sqrt(phase_psd[(f_hz >= lo) & (f_hz < hi)].sum()*df_hz))
                for lo, hi in BANDS_HZ}
    comparisons = []
    for average in (1, 2, 4, 8, 16):
        q = z.reshape(-1, average).mean(axis=1)
        p = np.unwrap(np.angle(q))
        # Mean true phase over the same bins gives aligned time coordinates.
        phase_mean = phase_rad.reshape(-1, average).mean(axis=1)
        difference = p-phase_mean
        difference -= difference[0]
        winding_error = np.rint(difference/(2*np.pi)).astype(int)
        comparisons.append(dict(extra_iq_average=average, sample_rate_hz=fs_hz/average,
            apparent_net_turns=float((p[-1]-p[0])/(2*np.pi)),
            final_integer_winding_error=int(winding_error[-1]),
            maximum_absolute_integer_winding_error=int(max(abs(winding_error)))))
    crossings = np.flatnonzero(abs(phase_rad) >= 4*np.pi)
    summary = dict(source=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        samples=len(z), sample_rate_hz=fs_hz, duration_s=len(z)/fs_hz,
        median_magnitude_adc_counts=float(np.median(magnitude)),
        minimum_magnitude_relative_to_median=float(magnitude.min()/np.median(magnitude)),
        max_adjacent_phase_step_rad=float(max(abs(steps_rad))),
        phase_min_relative_to_start_rad=float(phase_rad.min()),
        phase_max_relative_to_start_rad=float(phase_rad.max()),
        phase_peak_to_peak_rad=float(np.ptp(phase_rad)),
        phase_net_turns=float(phase_rad[-1]/(2*np.pi)),
        phase_standard_deviation_rad=float(phase_rad.std()),
        band_rms_rad=band_rms,
        first_two_turn_excursion_s=float(crossings[0]/fs_hz) if len(crossings) else None,
        iq_averaging_checks=comparisons)
    return dict(summary=summary, z=z, phase_rad=phase_rad, fs_hz=fs_hz,
                frequency_hz=f_hz, phase_psd=phase_psd, amplitude_psd=amplitude_psd)


def save(fig, name):
    for extension in ("png", "pdf"):
        fig.savefig(DIRECTORY / f"{name}.{extension}", dpi=170)
    plt.close(fig)


def plot_excursions(record):
    """Inspect threshold crossings without interpreting them as cycle slips."""
    phase = record["phase_rad"]
    fs_hz = record["fs_hz"]
    magnitude = abs(record["z"])
    first_crossing = np.flatnonzero(phase >= 4*np.pi)[0]
    peaks, _ = find_peaks(phase, height=4*np.pi, distance=round(20e-6*fs_hz))
    first_peak = peaks[np.argmin(abs(peaks-first_crossing))]
    centers = (first_peak, np.argmax(phase))
    edges = np.diff(np.r_[False, phase > 4*np.pi, False].astype(int))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    fig, axes = plt.subplots(3, 2, figsize=(12, 9), layout="constrained")
    summaries = []
    for column, (name, center) in enumerate(zip(("First range-crossing event", "Largest excursion"), centers)):
        pre = phase[center-round(300e-6*fs_hz):center-round(100e-6*fs_hz)]
        post = phase[center+round(100e-6*fs_hz):center+round(300e-6*fs_hz)]
        local_mean = (pre.mean()+post.mean())/2
        for row, halfwidth_us in enumerate((300, 30)):
            indices = np.arange(center-round(halfwidth_us*1e-6*fs_hz),
                                center+round(halfwidth_us*1e-6*fs_hz))
            time_us = (indices-center)/fs_hz*1e6
            axes[row, column].plot(time_us, phase[indices], lw=.8, color="#1769aa")
            axes[row, column].axhline(4*np.pi, color="#b64c26", ls="--", lw=1, label="Raw-phase observer upper range")
            axes[row, column].axhline(local_mean, color=".35", ls=":", lw=1, label="Local mean phase")
            axes[row, column].set(ylabel="Phase relative to capture start (rad)",
                                  xlabel="Time from excursion peak (µs)")
        axes[0, column].set_title(f"{name}, t = {center/fs_hz*1000:.6f} ms")
        axes[1, column].set_title("Resolved phase; no smoothing or detrending")
        axes[2, column].plot(time_us, magnitude[indices]/np.median(magnitude), lw=.8, color="#268477")
        axes[2, column].set(title="I/Q magnitude stays strong throughout the excursion",
                            ylabel="Magnitude / record median", xlabel="Time from excursion peak (µs)", ylim=(.85, 1.15))
        interval = np.flatnonzero((starts <= center) & (ends > center))[0]
        summaries.append(dict(name=name, peak_time_s=float(center/fs_hz),
            peak_phase_relative_to_capture_start_rad=float(phase[center]),
            local_mean_phase_rad=float(local_mean), peak_above_local_mean_rad=float(phase[center]-local_mean),
            pre_event_mean_rad=float(pre.mean()), post_event_mean_rad=float(post.mean()),
            pre_to_post_mean_change_rad=float(post.mean()-pre.mean()),
            mean_windows_us=[[-300, -100], [100, 300]],
            contiguous_duration_above_two_turn_range_s=float((ends[interval]-starts[interval])/fs_hz),
            minimum_magnitude_relative_to_median_in_60us=float(min(magnitude[indices])/np.median(magnitude))))
    axes[0, 0].legend(fontsize=8, loc="lower left")
    for ax in axes.flat:
        ax.grid(alpha=.2)
    fig.suptitle("Capture 3: brief phase excursions cross the diagnostic range and then return", fontsize=13)
    fig.supxlabel("Raw-phase FRA was OFF: the dashed line illustrates its ±2-turn range if armed at capture start.\n"
                  "These are not DAC rails. Beat phase alone cannot identify which laser caused the disturbance.", fontsize=9)
    save(fig, "shortest_iq_clipping_event_zoom")
    return summaries


def main():
    records = [read_record(n) for n in range(10)]
    colors = plt.get_cmap("tab10")(np.arange(10))
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, layout="constrained")
    for n, (record, color) in enumerate(zip(records, colors)):
        for ax, key in zip(axes, ("phase_psd", "amplitude_psd")):
            ax.semilogx(record["frequency_hz"], 10*np.log10(record[key]),
                        lw=.7, alpha=.75, color=color, label=str(n))
    axes[0].set(ylabel="Phase PSD (dB rad²/Hz)", ylim=(-120, -30),
                title="Unwrapped phase PSD: strong features near 65 and 86 kHz")
    axes[1].set(ylabel="Fractional amplitude PSD (dB/Hz)", xlabel="Fourier frequency (Hz)",
                ylim=(-125, -65), title="Magnitude fluctuations of the measured I/Q")
    for ax in axes:
        ax.set(xlim=(1000, 7680000))
        ax.grid(alpha=.2)
    axes[0].legend(title="Capture", ncol=10, fontsize=8, loc="lower left")
    fig.suptitle("15.36 MS/s captures: 8× tracking gain, FRA off", fontsize=13)
    fig.supxlabel("One-sided Welch PSD, Hann window, 234.375 Hz bin spacing; 7 overlapping segments per record.\n"
                  "No boxcar-response or alias correction; records are 17.07 ms each and are analyzed separately.", fontsize=9)
    save(fig, "shortest_iq_phase_psd")

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    r = records[3]
    phase = r["phase_rad"]
    fs_hz = r["fs_hz"]
    block = 256
    rows = phase.reshape(-1, block)
    t_ms = (np.arange(len(rows))+.5)*block/fs_hz*1000
    axes[0, 0].fill_between(t_ms, rows.min(axis=1), rows.max(axis=1), alpha=.35, color="#1769aa")
    axes[0, 0].plot(t_ms, rows.mean(axis=1), color="#1769aa", lw=.8)
    for bound in (-4*np.pi, 4*np.pi):
        axes[0, 0].axhline(bound, ls="--", color="#b64c26", lw=1)
    axes[0, 0].set(title="Capture 3: resolved phase relative to first sample",
                   xlabel="Time (ms)", ylabel="Unwrapped phase (rad)")
    peak = np.argmax(phase)
    sample = np.arange(max(0, peak-600), min(len(phase), peak+600))
    axes[0, 1].plot((sample-peak)/fs_hz*1e6, phase[sample], lw=1)
    axes[0, 1].axhline(4*np.pi, ls="--", color="#b64c26", lw=1)
    axes[0, 1].set(title="Largest positive excursion: returns to its local mean",
                   xlabel="Time from peak (µs)", ylabel="Unwrapped phase (rad)")
    q = r["z"].reshape(-1, 16).mean(axis=1)
    wrong = np.unwrap(np.angle(q))
    right = phase.reshape(-1, 16).mean(axis=1)
    wrong += right[0]-wrong[0]
    t_ms = (np.arange(len(q))+.5)*16/fs_hz*1000
    axes[1, 0].plot(t_ms, wrong/(2*np.pi), label="Average I/Q to 960 kS/s, then unwrap", color="#b64c26", lw=.7)
    axes[1, 0].plot(t_ms, right/(2*np.pi), label="Unwrap at 15.36 MS/s, then average phase", color="#1769aa", lw=.7)
    axes[1, 0].set(title="Same capture: slow I/Q falsely accumulates ~20 turns",
                   xlabel="Time (ms)", ylabel="Phase (turns)")
    axes[1, 0].legend(fontsize=8)
    for n, record in enumerate(records):
        axes[1, 1].plot(n, record["summary"]["phase_standard_deviation_rad"], "o", color=colors[n])
    axes[1, 1].set(title="Time-domain phase standard deviation; no linear detrending",
                   xlabel="Capture number", ylabel="Phase standard deviation (rad)", xticks=np.arange(10), ylim=(0, 1.8))
    for ax in axes.flat:
        ax.grid(alpha=.2)
    fig.suptitle("Fast sampling resolves oscillatory excursions and the earlier unwrap ambiguity", fontsize=13)
    fig.supxlabel("Dashed ±4π lines illustrate the raw-phase FRA observer range if armed at the first sample.\n"
                  "They are not DAC rails. No FRA tone was active in these records.", fontsize=9)
    save(fig, "shortest_iq_phase_time")

    excursions = plot_excursions(records[3])
    report = dict(conditions="User confirms 8x gain, FRA off; reference laser reportedly more stable than earlier batch.",
        records=[r["summary"] for r in records],
        capture_3_excursions=excursions,
        limitations=["Phase unwrapping is supported by strong magnitude and small adjacent steps; unresolved motion is not strictly excluded.",
                     "The 17 ms records do not characterize rare events over a seconds-long FRA acquisition.",
                     "Measured beat phase includes both lasers, electronics and feedback response.",
                     "Earlier slow records cannot be compared using their naive unwrapped phase PSDs."])
    (DIRECTORY/"shortest_iq_summary.json").write_text(json.dumps(report, indent=2)+"\n")
    columns = [records[0]["frequency_hz"]] + [r["phase_psd"] for r in records]
    np.savetxt(DIRECTORY/"shortest_iq_phase_psd.csv", np.column_stack(columns), delimiter=",",
               header="frequency_hz,"+",".join(f"capture_{n}_phase_rad2_per_hz" for n in range(10)), comments="")
    print("Saved ten-record phase analysis and spectral densities.")


if __name__ == "__main__":
    main()
