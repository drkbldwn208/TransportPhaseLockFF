"""Separate AM and PM near 1 kHz in the ten fast laser I/Q records.

Unwrap at 15.36 MS/s before filtering phase. Fit a sinusoid plus linear drift
to each record independently. The fitted frequency is a line-location estimate,
not a linewidth measurement. RF beat AM is not calibrated optical-intensity
noise; either laser or the detection chain can contribute to its magnitude.
"""
from pathlib import Path
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/low_frequency_iq_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal import butter, resample_poly, sosfiltfilt, welch

DIRECTORY = Path(__file__).resolve().parent / "10-13-IQ"


def fit_tone(time_s, values, frequency_hz):
    """Fit offset, drift, sine and cosine; all frequencies are in Hz."""
    centered_time_s = time_s-time_s.mean()
    basis = np.column_stack((np.ones(len(time_s)), centered_time_s,
                             np.cos(2*np.pi*frequency_hz*time_s),
                             np.sin(2*np.pi*frequency_hz*time_s)))
    coefficients = np.linalg.lstsq(basis, values, rcond=None)[0]
    residual = values-basis@coefficients
    return coefficients, basis@coefficients, float(np.mean(residual**2))


def main():
    phase_psds, amplitude_psds, iq_psds, unit_psds, rows = [], [], [], [], []
    for number in range(10):
        path = DIRECTORY/f"laser_iq_FPGA_shortest_{number}.npz"
        with np.load(path, allow_pickle=False) as data:
            z = data["i_adc_counts"]+1j*data["q_adc_counts"]
            fs_hz = float(data["sample_rate_hz"])
        phase_rad = np.unwrap(np.angle(z))
        amplitude_fraction = abs(z)/abs(z).mean()-1
        assert np.max(abs(np.diff(phase_rad))) < .6
        parameters = dict(fs=fs_hz, nperseg=131072, noverlap=65536, detrend="constant")
        f_hz, phase_psd = welch(phase_rad, **parameters)
        _, amplitude_psd = welch(amplitude_fraction, **parameters)
        phase_psds.append(phase_psd)
        amplitude_psds.append(amplitude_psd)
        for signal, collection in ((z/np.sqrt(np.mean(abs(z)**2)), iq_psds),
                                   (z/abs(z), unit_psds)):
            complex_f_hz, density = welch(signal, return_onesided=False, **parameters)
            positive = np.arange(1, len(density)//2)
            collection.append(density[positive]+density[-positive])

        # FIR decimation of scalar phase is safe after full-rate unwrapping.
        fit_fs_hz = fs_hz/128
        phase_slow = resample_poly(phase_rad-phase_rad.mean(), 1, 128, padtype="line")
        amplitude_slow = resample_poly(amplitude_fraction, 1, 128, padtype="line")
        time_s = np.arange(len(phase_slow))/fit_fs_hz
        keep = (time_s > .00025) & (time_s < time_s[-1]-.00025)
        time_s, phase_slow, amplitude_slow = time_s[keep], phase_slow[keep], amplitude_slow[keep]
        optimum = minimize_scalar(lambda frequency: fit_tone(time_s, phase_slow, frequency)[2],
                                   bounds=(1010, 1080), method="bounded")
        tone_hz = float(optimum.x)
        phase_coefficients, phase_fit, _ = fit_tone(time_s, phase_slow, tone_hz)
        amplitude_coefficients, _, _ = fit_tone(time_s, amplitude_slow, tone_hz)
        phase_peak_rad = float(np.hypot(*phase_coefficients[2:]))
        amplitude_peak_fraction = float(np.hypot(*amplitude_coefficients[2:]))
        band = (f_hz >= 500) & (f_hz <= 2000)
        df_hz = f_hz[1]-f_hz[0]
        rows.append(dict(source=path.name, fitted_tone_hz=tone_hz,
            phase_modulation_peak_rad=phase_peak_rad,
            frequency_modulation_peak_hz=tone_hz*phase_peak_rad,
            beat_amplitude_modulation_peak_fraction=amplitude_peak_fraction,
            small_signal_phase_sideband_dbc=float(10*np.log10(phase_peak_rad**2/4)),
            phase_rms_500_2000hz_rad=float(np.sqrt(phase_psd[band].sum()*df_hz)),
            beat_amplitude_rms_500_2000hz_fraction=float(np.sqrt(amplitude_psd[band].sum()*df_hz))))
        if number == 0:
            drift = phase_coefficients[0]+phase_coefficients[1]*(time_s-time_s.mean())
            shown_time_s = time_s
            shown_phase = sosfiltfilt(butter(4, 4000, fs=fit_fs_hz, output="sos"), phase_slow-drift)
            shown_fit = phase_fit-drift

    phase_psds, amplitude_psds = np.asarray(phase_psds), np.asarray(amplitude_psds)
    mean_phase, mean_amplitude = phase_psds.mean(axis=0), amplitude_psds.mean(axis=0)
    complex_f_hz = complex_f_hz[positive]
    mean_iq, mean_unit = np.mean(iq_psds, axis=0), np.mean(unit_psds, axis=0)
    near_line = (complex_f_hz >= 700) & (complex_f_hz <= 1400)
    normalization_change_db = float(10*np.log10(mean_unit[near_line].sum()/mean_iq[near_line].sum()))

    fig, axes = plt.subplots(3, 1, figsize=(10, 10), layout="constrained")
    for values, color, label in ((phase_psds, "#1769aa", "Phase, rad²/Hz"),
                                  (amplitude_psds, "#c35b25", "Fractional beat amplitude, 1/Hz")):
        lo, hi = np.percentile(values, (10, 90), axis=0)
        axes[0].fill_between(f_hz, 10*np.log10(lo), 10*np.log10(hi), color=color, alpha=.18)
        axes[0].plot(f_hz, 10*np.log10(values.mean(axis=0)), color=color, label=label)
    axes[0].set(xlim=(400, 6000), ylim=(-110, -40), xlabel="Fourier frequency (Hz)",
                ylabel="Modulation PSD (dB in stated units)", title="The ~1.04 kHz feature is predominantly phase modulation")
    axes[0].axvline(1043, color=".4", ls=":", lw=1)
    axes[0].legend(fontsize=9)
    axes[1].plot(complex_f_hz, 10*np.log10(mean_iq), label="Original I/Q: amplitude and phase", lw=2)
    axes[1].plot(complex_f_hz, 10*np.log10(mean_unit), "--", label="I/Q normalized to constant magnitude", lw=1.2)
    axes[1].set(xlim=(400, 6000), ylim=(-65, -45), xlabel="Offset frequency (Hz)",
                ylabel="Two sidebands / total power (dB/Hz)",
                title=f"Removing amplitude changes 700–1400 Hz sideband power by {normalization_change_db:+.3f} dB")
    axes[1].legend(fontsize=9)
    axes[2].plot(shown_time_s*1000, shown_phase, lw=1, label="Capture 0: unwrapped phase, 4 kHz low-pass")
    axes[2].plot(shown_time_s*1000, shown_fit, "--", color="#c35b25", lw=1.5, label="Fitted 1.04 kHz sinusoid")
    axes[2].set(xlim=(1, 7), ylim=(-.2, .2), xlabel="Time within capture (ms)",
                ylabel="Phase (rad)", title="The oscillation is present in phase itself, not only in the RF power spectrum")
    axes[2].legend(fontsize=9)
    for ax in axes:
        ax.grid(alpha=.2)
    fig.suptitle("Ten fast I/Q captures: 8× tracking gain, FRA off")
    fig.supxlabel("Welch bin spacing 117.19 Hz; 17.07 ms records. Shading: 10–90% record spread.\n"
                  "No attribution to individual lasers or electronics; captures need not coincide with analyzer traces.", fontsize=9)
    for extension in ("png", "pdf"):
        fig.savefig(DIRECTORY/f"low_frequency_am_pm.{extension}", dpi=170)
    plt.close(fig)
    band = (f_hz >= 500) & (f_hz <= 2000)
    report = dict(records=rows, psd_bin_hz=df_hz,
        phase_rms_500_2000hz_rad=float(np.sqrt(mean_phase[band].sum()*df_hz)),
        beat_amplitude_rms_500_2000hz_fraction=float(np.sqrt(mean_amplitude[band].sum()*df_hz)),
        amplitude_removal_change_700_1400hz_db=normalization_change_db,
        limitations=["Finite-record fitted tone frequency is not a linewidth measurement.",
            "RF magnitude includes both lasers and detection electronics; not calibrated lattice intensity noise.",
            "The normalized phasor spectrum is not a phase PSD for the large fast phase fluctuations.",
            "Historical analyzer records may describe different operating conditions."])
    (DIRECTORY/"low_frequency_am_pm.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
