"""Compare nine 960 kS/s laser I/Q records without assuming valid unwrapping.

The monitor averages complex I/Q BEFORE atan2. Its boxcar is not a strong
anti-alias filter. A phase-only phasor spectrum is useful even for large phase
motion, but it is NOT the phase PSD in rad^2/Hz except in the small-signal limit.
Separate records have unknown gaps and are never concatenated.
"""
from pathlib import Path
import hashlib
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/laser_iq_batch_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import welch

DIRECTORY = Path(__file__).resolve().parent / "10-13-IQ"


def folded_psd(values, sample_rate_hz):
    """Sum positive/negative spectral densities; units |values|^2/Hz.

    DC and the Nyquist bin are excluded. Removing the complex mean removes
    the carrier; normalizing z/abs(z) removes recorded magnitude fluctuations.
    """
    frequency_hz, density = welch(
        values, sample_rate_hz, nperseg=32768, noverlap=16384,
        detrend="constant", return_onesided=False, scaling="density")
    positive = np.arange(1, len(frequency_hz)//2)
    return frequency_hz[positive], density[positive] + density[-positive]


def read_record(path):
    with np.load(path, allow_pickle=False) as data:
        z = data["i_adc_counts"] + 1j*data["q_adc_counts"]
        sample_rate_hz = float(data["sample_rate_hz"])
        decimation_log2 = int(data["decimation_log2"])
    assert np.isfinite(z).all() and np.all(abs(z) > 0)
    assert sample_rate_hz == 245760000 / 2**decimation_log2
    magnitude = abs(z)
    median_magnitude = np.median(magnitude)
    unit = z / magnitude
    mean_angle_rad = np.angle(unit.mean())
    circular_deviation_rad = np.angle(unit * np.exp(-1j*mean_angle_rad))
    steps_rad = np.angle(z[1:]*z[:-1].conj())
    strong_pair = (magnitude[1:] > .5*median_magnitude) & (
        magnitude[:-1] > .5*median_magnitude)
    unwrap_checks = []
    for average in (1, 2, 4, 8):
        averaged = z[:len(z)//average*average].reshape(-1, average).mean(axis=1)
        turns = np.unwrap(np.angle(averaged))/(2*np.pi)
        unwrap_checks.append(dict(extra_average=average,
            apparent_net_turns=float(turns[-1]-turns[0]),
            apparent_span_turns=float(np.ptp(turns))))

    # Millisecond summaries reveal changing conditions without joining records.
    block_samples = round(.001*sample_rate_hz)
    blocks = len(z)//block_samples
    magnitude_blocks = magnitude[:blocks*block_samples].reshape(blocks, block_samples)
    unit_blocks = unit[:blocks*block_samples].reshape(blocks, block_samples)
    magnitude_fraction = magnitude_blocks.mean(axis=1)/median_magnitude
    circular_spread_rad = np.sqrt(-2*np.log(np.minimum(1, abs(unit_blocks.mean(axis=1)))))
    edges = np.diff(np.r_[False, magnitude_fraction < .5, False].astype(int))
    low_intervals = [dict(start_s=float(start*block_samples/sample_rate_hz),
                          end_s=float(end*block_samples/sample_rate_hz))
                     for start, end in zip(np.flatnonzero(edges == 1),
                                           np.flatnonzero(edges == -1))]
    frequency_hz, phase_only_psd = folded_psd(unit, sample_rate_hz)
    _, iq_psd = folded_psd(z / np.sqrt(np.mean(magnitude**2)), sample_rate_hz)
    _, amplitude_psd = folded_psd(magnitude / magnitude.mean(), sample_rate_hz)
    # Normalization check: integrated phasor fluctuation power is ~1-|<u>|^2.
    integrated_power = np.sum(phase_only_psd)*(frequency_hz[1]-frequency_hz[0])
    fluctuation_power = 1-abs(unit.mean())**2
    assert .75 < integrated_power/fluctuation_power < 1.25
    summary = dict(source=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        samples=len(z), sample_rate_hz=sample_rate_hz, decimation_log2=decimation_log2,
        duration_s=len(z)/sample_rate_hz, median_magnitude_adc_counts=float(median_magnitude),
        magnitude_fractional_std=float(magnitude.std()/magnitude.mean()),
        below_20_percent_median_fraction=float(np.mean(magnitude < .2*median_magnitude)),
        step_over_pi_half_fraction=float(np.mean(abs(steps_rad) > np.pi/2)),
        strong_magnitude_step_over_pi_half_fraction=float(np.mean(abs(steps_rad[strong_pair]) > np.pi/2)),
        circular_resultant=float(abs(unit.mean())),
        circular_spread_rad=float(np.sqrt(-2*np.log(abs(unit.mean())))),
        absolute_circular_deviation_95_percentile_rad=float(np.percentile(abs(circular_deviation_rad), 95)),
        unwrap_checks=unwrap_checks, low_magnitude_intervals_1ms_mean_below_half_median=low_intervals,
        phase_only_psd_integral=float(integrated_power),
        phase_only_time_domain_fluctuation_power=float(fluctuation_power))
    return dict(summary=summary, z=z, sample_rate_hz=sample_rate_hz,
        magnitude_fraction=magnitude_fraction, circular_spread_rad=circular_spread_rad,
        block_time_ms=(np.arange(blocks)+.5)*block_samples/sample_rate_hz*1000,
        frequency_hz=frequency_hz, phase_only_psd=phase_only_psd, iq_psd=iq_psd,
        amplitude_psd=amplitude_psd, circular_deviation_rad=circular_deviation_rad)


def save_figure(figure, stem):
    for extension in ("png", "pdf"):
        figure.savefig(DIRECTORY / f"{stem}.{extension}", dpi=170)
    plt.close(figure)


def main():
    records = [read_record(DIRECTORY / f"laser_iq_FPGA_shorter_{n}.npz") for n in range(1, 10)]
    colors = plt.get_cmap("tab10")(np.arange(9))
    plt.rcParams.update({"font.size": 10})
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), layout="constrained")
    for n, (record, color) in enumerate(zip(records, colors), 1):
        for ax, key in zip(axes, ("phase_only_psd", "iq_psd", "amplitude_psd")):
            ax.semilogx(record["frequency_hz"], 10*np.log10(record[key]),
                        color=color, lw=.6, alpha=.75, label=str(n))
    for ax in axes:
        ax.set(xlim=(1000, 480000), ylim=(-90, -35), xlabel="Offset frequency (Hz)")
        ax.grid(alpha=.2)
    axes[0].set(title="Phase-only phasor: magnitude removed, no phase unwrapping",
                ylabel="PSD of exp(iφ), dB/Hz")
    axes[1].set(title="Measured complex I/Q: includes amplitude and phase fluctuations",
                ylabel="PSD / mean |I+jQ|², dB/Hz")
    axes[2].set(title="Fractional magnitude fluctuations after complex averaging",
                ylabel="PSD of |I+jQ| / mean magnitude, dB/Hz")
    axes[0].legend(title="Capture", ncol=9, fontsize=8, loc="lower left")
    for f_hz, label in ((53050, "53"), (64000, "64"), (100000, "100"), (174800, "175 kHz")):
        axes[0].axvline(f_hz, color="black", alpha=.25, lw=.8)
        axes[0].text(f_hz, -36, label, ha="center", va="top", fontsize=8)
    fig.suptitle("Nine 960 kS/s I/Q captures; 0.273 s each", fontsize=13)
    fig.supxlabel("Positive and negative sidebands summed; Welch Hann windows, 29.30 Hz bins.\n"
                  "These are phasor spectra, not calibrated Sφ in rad²/Hz. Monitor aliasing is not corrected.", fontsize=9)
    save_figure(fig, "fast_iq_batch_spectra")

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), layout="constrained")
    for n, (record, color) in enumerate(zip(records, colors), 1):
        axes[0].plot(record["block_time_ms"], record["magnitude_fraction"], color=color, lw=.9, label=str(n))
        axes[1].plot(record["block_time_ms"], record["circular_spread_rad"], color=color, lw=.9)
        summary = record["summary"]
        axes[2].plot(n, summary["step_over_pi_half_fraction"]*100, "o", color=color)
        axes[2].plot(n, summary["strong_magnitude_step_over_pi_half_fraction"]*100, "x", color=color)
    axes[0].set(title="Magnitude, averaged in 1 ms blocks", ylabel="Magnitude / record median", xlabel="Time within each record (ms)")
    axes[0].legend(title="Capture", ncol=9, fontsize=8, loc="lower right")
    axes[1].set(title="Circular phase spread in 1 ms blocks; no unwrapping",
                ylabel="√(−2 ln |mean exp(iφ)|), rad", xlabel="Time within each record (ms)")
    axes[2].plot([], [], "ko", label="All adjacent pairs")
    axes[2].plot([], [], "kx", label="Both magnitudes > 50% of record median")
    axes[2].set(title="Large phase steps persist at strong measured magnitude",
                ylabel="Adjacent phase steps > π/2 (%)", xlabel="Capture number", xticks=np.arange(1, 10))
    axes[2].legend(fontsize=9)
    for ax in axes:
        ax.grid(alpha=.2)
    fig.suptitle("Rapid phase motion occurs in every capture", fontsize=13)
    fig.supxlabel("Times reset between separate records; neither capture gaps nor loop settings are saved in these NPZ files.", fontsize=9)
    save_figure(fig, "fast_iq_batch_time")

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), layout="constrained")
    for column, number in enumerate((1, 2)):
        record = records[number-1]
        fs_hz = record["sample_rate_hz"]
        samples = np.arange(round(.01*fs_hz), round(.0101*fs_hz))
        time_us = (samples/fs_hz-.01)*1e6
        z = record["z"]
        axes[0, column].plot(time_us, record["circular_deviation_rad"][samples], ".-", lw=.6, ms=3)
        axes[0, column].set(title=f"Capture {number}: 100 µs window at t = 10 ms",
                            ylabel="Principal phase about circular mean (rad)", ylim=(-np.pi, np.pi))
        axes[1, column].plot(time_us, abs(z[samples])/np.median(abs(z)), ".-", lw=.6, ms=3)
        axes[1, column].set(ylabel="Magnitude / record median", ylim=(0, 1.2))
    for ax in axes.flat:
        ax.set(xlabel="Time within window (µs)")
        ax.grid(alpha=.2)
    fig.suptitle("Sample-resolved phase and magnitude; sample spacing 1.042 µs", fontsize=13)
    fig.supxlabel("Principal phase is modulo 2π. Lines joining samples do not establish physical winding direction.", fontsize=9)
    save_figure(fig, "fast_iq_batch_zoom")

    output = dict(records=[record["summary"] for record in records],
        conditions="Loop settings and FRA state not stored; awaiting user confirmation.",
        limitations=["A physical cycle-slip count cannot be established from these records.",
                     "Extra averaging disagreement is a warning, not proof every original unwrap step is wrong.",
                     "Normalization removes recorded amplitude noise, not PM-to-AM conversion before capture.",
                     "Monitor boxcar aliasing and complex averaging can distort spectra and magnitude.",
                     "Circular spread is not the RMS of unwrapped phase.",
                     "Passive I/Q spectra do not independently measure loop gain or unity-gain frequency."])
    (DIRECTORY / "fast_iq_batch_summary.json").write_text(json.dumps(output, indent=2)+"\n")
    for record in records:
        s = record["summary"]
        print(s["source"], "circular spread =", round(s["circular_spread_rad"], 3),
              "rad; 95% abs principal phase =", round(s["absolute_circular_deviation_95_percentile_rad"], 3),
              "rad; low-magnitude intervals:", s["low_magnitude_intervals_1ms_mean_below_half_median"])


if __name__ == "__main__":
    main()
