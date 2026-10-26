"""Compare ADF4108 and FPGA lock phase/AM dynamics in fast I/Q captures.

The ADF data use a 1 GHz beat, folded to 966.08 MHz by the 1.96608 GS/s
real ADC. Its DDC image at 33.92 MHz aliases to +3.2 MHz in the monitor.
An offline complex low-pass removes that separated image before atan2.
Both batches receive the same filter; phase is unwrapped at 15.36 MS/s.
No further complex decimation, ellipse calibration, or noise-floor subtraction.

Spectra are one-sided, per Hz. a = |I+jQ|/mean(|I+jQ|)-1 is fractional
RF beat amplitude, not optical RIN. Cross spectrum = conj(A)*Phi. Physical
beat phase has the opposite sign in Nyquist zone 2, so we reverse PLL phase.
Correlation alone cannot establish AM -> PM causality inside a feedback loop.
"""
from pathlib import Path
import json
import os
import re

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pll_fpga_iq_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, sosfiltfilt, welch, csd, windows
from scipy.ndimage import gaussian_filter1d

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "10-14-IQ"
FS_HZ = 15.36e6
FFT_LENGTH = 65536
EDGE_SAMPLES = 4096
LOWPASS_HZ = 2e6
BANDS_HZ = [(1000, 10000), (10000, 100000), (100000, 1000000)]
COLORS = {"FPGA": "#1769aa", "PLL": "#c45324", "PLL_quiet": "#268477"}


def load_record(kind, number, cutoff_hz=LOWPASS_HZ):
    folder = "10-14-IQ" if kind == "PLL" else "10-13-IQ"
    path = ROOT / folder / f"laser_iq_{kind}_shortest_{number}.npz"
    with np.load(path, allow_pickle=False) as data:
        z = data["i_adc_counts"].astype(float) + 1j*data["q_adc_counts"]
        assert float(data["sample_rate_hz"]) == FS_HZ
        assert int(data["decimation_log2"]) == 4
    magnitude = abs(z)
    steps = np.angle(z[1:]*z[:-1].conj())
    # The image is spectrally separated from the useful <1 MHz dynamics.
    # Zero-phase filtering is for offline measurement, not a feedback filter.
    filtered_z = sosfiltfilt(butter(8, cutoff_hz, fs=FS_HZ, output="sos"), z)
    filtered_z = filtered_z[EDGE_SAMPLES:-EDGE_SAMPLES]
    phase_rad = np.unwrap(np.angle(filtered_z)) * (-1 if kind == "PLL" else 1)
    phase_rad -= phase_rad.mean()
    amplitude = abs(filtered_z)/abs(filtered_z).mean()-1
    # 5 kHz smoothing distinguishes persistent phase drift from fast excursions.
    slow_phase = sosfiltfilt(butter(3, 5000, fs=FS_HZ, output="sos"), phase_rad)
    margin = round(.001*FS_HZ)
    slow_span_turns = np.ptp(slow_phase[margin:-margin])/(2*np.pi)
    reliable = bool(magnitude.min()/np.median(magnitude) > .5 and max(abs(steps)) < 1)
    quiet = reliable and slow_span_turns < 1
    summary = dict(source=path.name, reliable_unwrap=reliable, quiet_subset=bool(quiet),
        mean_iq_magnitude_adc_counts=float(magnitude.mean()),
        minimum_magnitude_relative_to_median=float(magnitude.min()/np.median(magnitude)),
        raw_amplitude_rms_fraction=float(magnitude.std()/magnitude.mean()),
        maximum_raw_phase_step_rad=float(max(abs(steps))),
        filtered_phase_std_rad=float(phase_rad.std()) if reliable else None,
        lowpass_5khz_span_turns=float(slow_span_turns) if reliable else None,
        endpoint_change_turns=float((slow_phase[-margin:].mean()-slow_phase[:margin].mean())/(2*np.pi)) if reliable else None)
    return dict(number=number, kind=kind, z=z, filtered_z=filtered_z,
                phase=phase_rad, amplitude=amplitude, slow_phase=slow_phase, summary=summary)


def fft_segments(values):
    """Seven (six after trimming) 50%-overlapping Hann-windowed segments."""
    segments = np.lib.stride_tricks.sliding_window_view(values, FFT_LENGTH)[::FFT_LENGTH//2]
    window = windows.hann(FFT_LENGTH, sym=False)
    centered = segments-segments.mean(axis=1, keepdims=True)
    fourier = np.fft.rfft(centered*window, axis=-1)
    scale = np.full(fourier.shape[-1], 2/(FS_HZ*np.sum(window**2)))
    scale[[0, -1]] /= 2
    return fourier*np.sqrt(scale)


def band_statistics(f_hz, phase_psd, amplitude_psd, cross_psd):
    coherence = abs(cross_psd)**2/(phase_psd*amplitude_psd)
    rows = []
    for lo, hi in BANDS_HZ:
        keep = (f_hz >= lo) & (f_hz < hi)
        phase_power = phase_psd[keep].sum()*(f_hz[1]-f_hz[0])
        rows.append(dict(band_hz=[lo, hi], phase_rms_rad=float(np.sqrt(phase_power)),
            amplitude_rms_fraction=float(np.sqrt(amplitude_psd[keep].sum()*(f_hz[1]-f_hz[0]))),
            phase_weighted_coherence=float(np.sum(coherence[keep]*phase_psd[keep])/np.sum(phase_psd[keep]))))
    return rows


def analyze_group(records, label):
    phase_fft = np.asarray([fft_segments(r["phase"]) for r in records])
    amplitude_fft = np.asarray([fft_segments(r["amplitude"]) for r in records])
    per_phase = np.mean(abs(phase_fft)**2, axis=1)
    per_amplitude = np.mean(abs(amplitude_fft)**2, axis=1)
    per_cross = np.mean(amplitude_fft.conj()*phase_fft, axis=1)
    f_hz = np.fft.rfftfreq(FFT_LENGTH, 1/FS_HZ)
    phase_psd, amplitude_psd, cross_psd = [x.mean(axis=0) for x in (per_phase, per_amplitude, per_cross)]
    coherence = abs(cross_psd)**2/(phase_psd*amplitude_psd)
    assert np.max(coherence) < 1+1e-12
    # Match SciPy and its CSD sign and density conventions independently.
    kwargs = dict(fs=FS_HZ, window="hann", nperseg=FFT_LENGTH, noverlap=FFT_LENGTH//2)
    _, check_phase = welch(records[0]["phase"], **kwargs)
    _, check_cross = csd(records[0]["amplitude"], records[0]["phase"], **kwargs)
    assert np.allclose(check_phase, per_phase[0], rtol=1e-9, atol=1e-18)
    assert np.allclose(check_cross, per_cross[0], rtol=1e-8, atol=1e-18)
    rows = band_statistics(f_hz, phase_psd, amplitude_psd, cross_psd)

    # Cluster bootstrap whole independent captures, never individual samples.
    rng = np.random.default_rng(4108)
    bootstrap = []
    for _ in range(400):
        index = rng.integers(len(records), size=len(records))
        stats = band_statistics(f_hz, per_phase[index].mean(0), per_amplitude[index].mean(0), per_cross[index].mean(0))
        bootstrap.append([[row["phase_rms_rad"], row["amplitude_rms_fraction"]] for row in stats])
    bounds = np.percentile(bootstrap, [2.5, 97.5], axis=0)

    # Mismatch amplitude and phase records to measure accidental correlation.
    # Stable common spectral lines can survive mismatching: this is deliberately
    # a conservative control, not a proof of causality or a universal p-value.
    use = f_hz <= 1e6
    cross_pairs = np.einsum("isf,jsf->ijf", amplitude_fft[:, :, use].conj(), phase_fft[:, :, use])/phase_fft.shape[1]
    null_cross = []
    for _ in range(300):
        order = rng.permutation(len(records))
        while np.any(order == np.arange(len(records))):
            order = rng.permutation(len(records))
        null_cross.append(cross_pairs[np.arange(len(records)), order].mean(0))
    null_cross = np.asarray(null_cross)
    null_coherence = abs(null_cross)**2/(phase_psd[use]*amplitude_psd[use])
    for index, row in enumerate(rows):
        row["bootstrap_95_percent"] = {key: bounds[:, index, j].tolist() for j, key in enumerate(
            ("phase_rms_rad", "amplitude_rms_fraction"))}
        lo, hi = row["band_hz"]
        band = (f_hz[use] >= lo) & (f_hz[use] < hi)
        null_weighted = np.sum(null_coherence[:, band]*phase_psd[use][band], axis=1)/phase_psd[use][band].sum()
        row["mismatched_record_coherence_median_95th"] = np.percentile(null_weighted, [50, 95]).tolist()
    return dict(label=label, count=len(records), record_numbers=[r["number"] for r in records],
                f=f_hz, phase=phase_psd, amplitude=amplitude_psd, cross=cross_psd,
                coherence=coherence, per_phase=per_phase, per_amplitude=per_amplitude,
                null_cross=null_cross, bands=rows)


def save_plot(fig, name):
    for extension in ("png", "pdf"):
        fig.savefig(OUTPUT/f"{name}.{extension}", dpi=170)
    plt.close(fig)


def make_plots(groups, records):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    labels = {"FPGA": "FPGA: 10 records", "PLL": "ADF4108: 9 resolved records", "PLL_quiet": "ADF4108: 4 quiet records"}
    for name, group in groups.items():
        f = group["f"]
        for ax, quantity in zip(axes[0], ("phase", "amplitude")):
            ax.semilogx(f, 10*np.log10(group[quantity]), color=COLORS[name], alpha=.9,
                        lw=1.2, ls="--" if name == "PLL_quiet" else "-", label=labels[name])
        # Average the complex CSD before computing coherence; never average |C|.
        p, a, c = [gaussian_filter1d(group[k], 2) for k in ("phase", "amplitude", "cross")]
        axes[1, 0].semilogx(f, abs(c)**2/(p*a), color=COLORS[name], label=labels[name])
        axes[1, 1].loglog(f, np.maximum(abs(c), 1e-30), color=COLORS[name], label=labels[name])
    axes[0, 0].set(ylabel="Phase PSD (dB rad²/Hz)", title="Phase: more slow motion in PLL; stronger 65–86 kHz FPGA peaks", ylim=(-100, -20))
    axes[0, 1].set(ylabel="Fractional beat-amplitude PSD (dB/Hz)", title="Below 1 MHz the amplitude noise is similar", ylim=(-112, -70))
    axes[1, 0].set(ylabel="Magnitude-squared AM–phase coherence", ylim=(0, 1), title="Correlation depends strongly on Fourier frequency")
    axes[1, 1].set(ylabel="|AM–phase cross-PSD| (rad/Hz)", ylim=(1e-11, 1e-5), title="Absolute AM–phase cross-spectrum")
    for ax in axes.flat:
        ax.set(xlim=(700, 1e6), xlabel="Fourier frequency (Hz)")
        ax.grid(alpha=.2)
    axes[0, 1].legend(fontsize=8)
    fig.suptitle("ADF4108 at 1 GHz versus FPGA at 800 MHz: matched processing")
    fig.supxlabel("Both: 15.36 MS/s, 17.07 ms records; 2 MHz complex low-pass removes the PLL's 3.2 MHz mixer image.\n"
                  "Spectra: 234.375 Hz bins; lower panels smoothed over ~1.1 kHz FWHM. PLL record 1 excluded: unwrap ambiguous.", fontsize=9)
    save_plot(fig, "pll_fpga_spectra_cross")

    fig, axes = plt.subplots(3, 2, figsize=(12, 9), layout="constrained")
    for kind, column in (("FPGA", 0), ("PLL", 1)):
        valid = [r for r in records[kind] if r["summary"]["reliable_unwrap"]]
        for r in valid:
            # Scalar phase is downsampled only for plotting after extraction.
            t = (np.arange(len(r["phase"]))+EDGE_SAMPLES)/FS_HZ*1000
            margin = round(.001*FS_HZ)
            axes[0, column].plot(t[margin:-margin:256], r["slow_phase"][margin:-margin:256]/(2*np.pi), lw=.7, label=str(r["number"]))
        r = records[kind][3 if kind == "PLL" else 2]
        sample = (np.arange(len(r["phase"]))/FS_HZ >= .004) & (np.arange(len(r["phase"]))/FS_HZ <= .00415)
        t_us = (np.arange(len(r["phase"]))[sample]/FS_HZ-.004)*1e6
        axes[1, column].plot(t_us, r["phase"][sample], lw=.8, color=COLORS[kind])
        axes[2, column].plot(t_us, 100*r["amplitude"][sample], lw=.8, color=COLORS[kind])
        axes[0, column].set(title=f"{kind}: 5 kHz low-pass phase, all resolved records", xlabel="Time (ms)", ylabel="Phase about record mean (turns)")
        axes[0, column].legend(ncol=5, fontsize=7, title="Record")
        axes[1, column].set(title=f"Example quiet capture {r['number']}: fast phase motion", ylabel="Phase (rad)", xlabel="Time within 150 µs excerpt (µs)", ylim=(-6, 6))
        axes[2, column].set(ylabel="Fractional beat amplitude (%)", xlabel="Time within excerpt (µs)", ylim=(-7, 7))
    for ax in axes.flat:
        ax.grid(alpha=.2)
    fig.suptitle("Phase drift and fast amplitude dynamics are distinct")
    fig.supxlabel("Phase sign corrected for the PLL capture's second Nyquist zone. Upper panels have different vertical scales.\n"
                  "Examples were selected by small slow phase drift; the full resolved batch remains in the spectral comparison.", fontsize=9)
    save_plot(fig, "pll_fpga_time_dynamics")

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), layout="constrained")
    for kind in ("PLL", "FPGA"):
        r = records[kind][0]
        for z, style, title in ((r["z"], "-", "original"), (r["filtered_z"], "--", "2 MHz low-pass")):
            f, p = welch(z/np.sqrt(np.mean(abs(z)**2)), fs=FS_HZ, nperseg=65536, return_onesided=False, detrend=False)
            order = np.argsort(f)
            axes[0].plot(f[order]/1e6, 10*np.log10(p[order]), style, color=COLORS[kind], lw=.9, label=f"{kind}, {title}")
            f, p = welch(abs(z)/abs(z).mean()-1, fs=FS_HZ, nperseg=65536)
            axes[1].semilogx(f, 10*np.log10(p), style, color=COLORS[kind], lw=.9, label=f"{kind}, {title}")
    axes[0].axvline(3.2, color=".3", ls=":", lw=1)
    axes[0].set(xlabel="Complex baseband frequency (MHz)", ylabel="Complex PSD / total power (dB/Hz)", xlim=(-5, 5), ylim=(-140, -30),
                title="PLL: unwanted +3.2 MHz image from the real ADC's near-Nyquist input")
    axes[1].set(xlabel="Fourier frequency (Hz)", ylabel="Fractional beat-amplitude PSD (dB/Hz)", xlim=(1000, 7e6), ylim=(-130, -65),
                title="The large extra high-frequency amplitude ripple mostly disappears when the image is removed")
    for ax in axes:
        ax.legend(fontsize=8, ncol=2)
        ax.grid(alpha=.2)
    fig.suptitle("Measurement artifact check: matched offline image rejection")
    save_plot(fig, "pll_mixer_image_check")


def image_prediction():
    text = (ROOT.parent/"TransportPhaseLockFF.srcs/sources_1/new/laser_pll_fir_coeffs.vh").read_text()
    coefficients = np.array([(-1 if sign else 1)*int(value) for sign, value in re.findall(r"fir_coefficient = (-?)18'sd(\d+)", text)])
    assert len(coefficients) == 32
    image_hz, adc_fs_hz, fabric_fs_hz = 33.92e6, 1966.08e6, 245.76e6
    fir_gain = abs(np.sum(coefficients*np.exp(-2j*np.pi*image_hz/adc_fs_hz*np.arange(32))))/sum(coefficients)
    boxcar_gain = abs(np.sin(np.pi*16*image_hz/fabric_fs_hz)/(16*np.sin(np.pi*image_hz/fabric_fs_hz)))
    return dict(beat_hz=1e9, reference_hz=966.08e6, adc_fs_hz=adc_fs_hz,
                image_before_monitor_hz=image_hz, image_after_monitor_hz=3.2e6,
                fir_relative_gain=float(fir_gain), monitor_relative_gain=float(boxcar_gain),
                predicted_image_amplitude_ratio=float(fir_gain*boxcar_gain),
                predicted_spurious_am_rms_fraction=float(fir_gain*boxcar_gain/np.sqrt(2)))


def main():
    records = {kind: [load_record(kind, n) for n in range(10)] for kind in ("FPGA", "PLL")}
    groups = {kind: analyze_group([r for r in batch if r["summary"]["reliable_unwrap"]], kind) for kind, batch in records.items()}
    groups["PLL_quiet"] = analyze_group([r for r in records["PLL"] if r["summary"]["quiet_subset"]], "PLL_quiet")
    make_plots(groups, records)
    # A mixer image is a conjugated copy, not independent amplitude noise.
    # Verify both that relation and its amplitude against the actual RTL FIR.
    image_fits = []
    for r in records["PLL"]:
        if not r["summary"]["quiet_subset"]:
            continue
        t_s = np.arange(len(r["z"]))/FS_HZ
        shifted = r["z"]*np.exp(-2j*np.pi*3.2e6*t_s)
        image = sosfiltfilt(butter(8, LOWPASS_HZ, fs=FS_HZ, output="sos"), shifted)[EDGE_SAMPLES:-EDGE_SAMPLES]
        desired_conjugate = r["filtered_z"].conj()
        gain = np.vdot(desired_conjugate, image)/np.vdot(desired_conjugate, desired_conjugate)
        image_fits.append(dict(record=r["number"], measured_image_amplitude_ratio=float(abs(gain)),
            image_power_explained_by_conjugated_carrier=float(1-np.mean(abs(image-gain*desired_conjugate)**2)/np.mean(abs(image)**2))))
    report = dict(image_model=image_prediction(), image_fits=image_fits,
        records={k: [r["summary"] for r in v] for k, v in records.items()},
        groups={k: {field: g[field] for field in ("count", "record_numbers", "bands")} for k, g in groups.items()},
        method=dict(sample_rate_hz=FS_HZ, original_samples=262144, complex_lowpass_hz=LOWPASS_HZ,
                    trimmed_samples_each_end=EDGE_SAMPLES, fft_length=FFT_LENGTH, fft_bin_hz=FS_HZ/FFT_LENGTH,
                    quiet_rule="5 kHz filtered phase spans <1 turn, omitting 1 ms at both edges",
                    cross_convention="conj(FFT fractional amplitude) * FFT physical beat phase; PLL phase sign reversed",
                    coherent_fraction_metric="integral(|S_a_phi|^2/S_aa) / integral(S_phi_phi), positive finite-sample bias",
                    null_control="mismatch whole AM/phase records; 300 derangements; not a causal test"),
        limitations=["Different carrier frequencies and ~10x measured I/Q magnitude; not a controlled detector swap.",
            "Analog settings reportedly unchanged; reference-laser conditions not independently measured.",
            "Capture 1 has deep signal minima and phase steps near pi; its total phase winding is not trustworthy.",
            "Quiet-record selection is explicitly conditional, not representative of all PLL acquisition time.",
            "Beat AM is not calibrated optical intensity noise; correlation cannot determine coupling direction.",
            "Only the <1 MHz comparison is interpreted after image rejection; do not infer absolute linewidth."])
    (OUTPUT/"pll_fpga_iq_comparison.json").write_text(json.dumps(report, indent=2)+"\n")
    arrays = {}
    for key, group in groups.items():
        for field in ("f", "phase", "amplitude", "cross", "coherence"):
            arrays[f"{key}_{field}"] = group[field]
    np.savez_compressed(OUTPUT/"pll_fpga_iq_spectra.npz", **arrays)
    print(json.dumps({"image_model": report["image_model"], "groups": report["groups"]}, indent=2))


if __name__ == "__main__":
    main()
