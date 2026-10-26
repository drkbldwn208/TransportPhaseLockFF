"""Convert resolved beat phase to frequency error, with explicit time averaging.

I+jQ has phase theta_beat-theta_reference. Thus dphi/dt/(2*pi) is f_beat-f_ref,
the opposite sign to the PLL's reference-minus-beat frequency status register.
Unwrap at 15.36 MS/s FIRST. An N-sample difference then measures frequency
averaged over N/fs seconds, timestamped at the interval midpoint. This avoids
the cycle ambiguity of averaging complex I/Q before taking its phase.
"""
from pathlib import Path
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/instantaneous_frequency_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks

DIRECTORY = Path(__file__).resolve().parent / "10-13-IQ"


def frequency_from_phase(phase_rad, fs_hz, interval_samples):
    """Return interval midpoints (s) and interval-mean frequency error (Hz)."""
    frequency_hz = np.diff(phase_rad) if interval_samples == 1 else (
        phase_rad[interval_samples:] - phase_rad[:-interval_samples])
    frequency_hz = frequency_hz * fs_hz / (2*np.pi*interval_samples)
    time_s = (np.arange(len(frequency_hz))+interval_samples/2)/fs_hz
    return time_s, frequency_hz


def main():
    records = []
    all_spans_rad = []
    for number in range(10):
        path = DIRECTORY / f"laser_iq_FPGA_shortest_{number}.npz"
        with np.load(path, allow_pickle=False) as d:
            z = d["i_adc_counts"]+1j*d["q_adc_counts"]
            fs_hz = float(d["sample_rate_hz"])
        phase_rad = np.unwrap(np.angle(z))
        phase_rad -= phase_rad[0]
        assert max(abs(np.diff(phase_rad))) < .6
        # Integrating the unsmoothed derivative reconstructs the measured phase.
        _, frequency_hz = frequency_from_phase(phase_rad, fs_hz, 1)
        assert np.allclose(np.cumsum(frequency_hz)*2*np.pi/fs_hz, phase_rad[1:], atol=1e-9)
        stats = []
        for interval in (1, 8, 16):
            _, frequency_hz = frequency_from_phase(phase_rad, fs_hz, interval)
            stats.append(dict(interval_samples=interval, averaging_interval_s=interval/fs_hz,
                standard_deviation_hz=float(frequency_hz.std()),
                percentiles_1_5_50_95_99_hz=np.percentile(frequency_hz, [1, 5, 50, 95, 99]).tolist()))
        block_samples = round(100e-6*fs_hz)
        blocks = phase_rad[:len(phase_rad)//block_samples*block_samples].reshape(-1, block_samples)
        spans_rad = np.ptp(blocks, axis=1)
        all_spans_rad.extend(spans_rad)
        records.append(dict(source=path.name,
            mean_frequency_from_endpoints_hz=float((phase_rad[-1]-phase_rad[0])*fs_hz/(2*np.pi*(len(phase_rad)-1))),
            fraction_100us_windows_phase_span_over_two_pi=float(np.mean(spans_rad > 2*np.pi)),
            frequency_statistics=stats))
        if number == 3:
            shown_phase = phase_rad.copy()
    phase_rad = shown_phase
    time_s = np.arange(len(phase_rad))/fs_hz
    first_crossing = np.flatnonzero(phase_rad > 4*np.pi)[0]
    peaks, _ = find_peaks(phase_rad, height=4*np.pi, distance=round(20e-6*fs_hz))
    first_peak = peaks[np.argmin(abs(peaks-first_crossing))]
    centers_s = (1.05e-3, first_peak/fs_hz, np.argmax(phase_rad)/fs_hz)
    names = ("Ordinary interval", "First range-crossing event", "Largest phase excursion")
    derivatives = [frequency_from_phase(phase_rad, fs_hz, interval) for interval in (8, 16)]
    fig, axes = plt.subplots(3, 3, figsize=(14, 10), layout="constrained")
    windows = []
    for col, (name, center_s) in enumerate(zip(names, centers_s)):
        phase_mask = abs(time_s-center_s) < 100e-6
        # Remove only a constant for a readable phase axis; frequency is unchanged.
        phase_mean_rad = phase_rad[phase_mask].mean()
        axes[0, col].plot((time_s[phase_mask]-center_s)*1e6,
                          (phase_rad[phase_mask]-phase_mean_rad)/(2*np.pi), lw=.8, color="#1769aa")
        axes[0, col].axhline(0, color=".4", lw=.6)
        axes[0, col].set(title=f"{name}\nt = {center_s*1000:.6f} ms",
                         ylabel="Phase about window mean (turns)", xlabel="Time from window center (µs)", ylim=(-1.65, 1.75))
        window_stats = dict(name=name, center_s=float(center_s),
            phase_peak_to_peak_turns=float(np.ptp(phase_rad[phase_mask])/(2*np.pi)))
        for row, width_us in ((1, 100), (2, 30)):
            for (t_s, freq_hz), interval, color in zip(derivatives, (8, 16), ("#1769aa", "#df7c2a")):
                mask = abs(t_s-center_s) < width_us*1e-6
                axes[row, col].plot((t_s[mask]-center_s)*1e6, freq_hz[mask]/1000,
                                    lw=.75, color=color, alpha=.85,
                                    label=f"{interval/fs_hz*1e6:.3f} µs frequency average")
                if row == 2 and interval == 8:
                    window_stats.update(zoom_min_frequency_hz=float(freq_hz[mask].min()),
                                        zoom_max_frequency_hz=float(freq_hz[mask].max()))
            axes[row, col].axhline(0, color=".4", lw=.6)
            axes[row, col].set(ylabel="Beat − reference frequency (kHz)",
                               xlabel="Time from window center (µs)", ylim=(-1150, 1150))
        windows.append(window_stats)
    axes[1, 0].legend(fontsize=8, loc="lower left")
    for ax in axes.flat:
        ax.grid(alpha=.2)
    fig.suptitle("Capture 3: unwrapped phase converted to instantaneous frequency error", fontsize=14)
    fig.supxlabel("Δf = [φ(t+τ/2) − φ(t−τ/2)] / (2πτ). Positive means beat frequency above the reference.\n"
                  "Finite time averaging limits derivative noise; it does not imply an instantaneous DC detuning. No drift is removed.", fontsize=9)
    for extension in ("png", "pdf"):
        fig.savefig(DIRECTORY/f"shortest_iq_instantaneous_frequency.{extension}", dpi=170)
    plt.close(fig)
    report = dict(sign="f_beat - f_reference; opposite to PLL frequency status", source_sample_rate_hz=fs_hz,
        records=records, plotted_capture_3_windows=windows,
        median_100us_phase_span_rad=float(np.median(all_spans_rad)),
        fraction_100us_phase_span_over_two_pi=float(np.mean(np.array(all_spans_rad) > 2*np.pi)),
        limitations=["Derived from recorded beat phase, not a measurement of either optical laser frequency separately.",
                     "Differentiation magnifies fast measurement noise; statistics depend on averaging interval.",
                     "N-sample frequency averaging is applied after full-rate phase unwrapping.",
                     "Phase spans are peak-to-peak, not RMS or persistent cycle-slip counts."])
    (DIRECTORY/"shortest_iq_instantaneous_frequency.json").write_text(json.dumps(report, indent=2)+"\n")
    t_s, freq_hz = derivatives[0]
    # Save the complete estimate for independent inspection and plotting.
    np.savez_compressed(DIRECTORY/"shortest_3_frequency_derived.npz", time_s=t_s,
                        beat_minus_reference_hz=freq_hz, averaging_interval_s=8/fs_hz)
    print(json.dumps({k:v for k,v in report.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    main()
