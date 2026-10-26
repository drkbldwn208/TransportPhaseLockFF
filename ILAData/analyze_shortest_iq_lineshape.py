"""Separate the measured beat's narrow carrier from its phase-noise pedestal.

Use the ten 17 ms captures independently, without phase unwrapping or drift
subtraction. Unit phasors remove AM. The finite-record coherent fraction is
|mean(exp(i*phase))|^2; it is not a long-term absolute laser-linewidth estimate.
Occupied bandwidths use a rectangular-window FFT for exact power accounting.
Hann-window spectra are used only for display. No receiver correction is made.
"""
from pathlib import Path
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/laser_lineshape_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import periodogram

DIRECTORY = Path(__file__).resolve().parent / "10-13-IQ"


def main():
    records, spectra, cumulative_curves = [], [], []
    halfwidth_hz = np.geomspace(60, 3e6, 600)
    for number in range(10):
        path = DIRECTORY / f"laser_iq_FPGA_shortest_{number}.npz"
        with np.load(path, allow_pickle=False) as data:
            z = data["i_adc_counts"] + 1j*data["q_adc_counts"]
            sample_rate_hz = float(data["sample_rate_hz"])
        assert np.isfinite(z).all() and np.min(abs(z)) > 0
        phasor = z/abs(z)
        frequency_hz = np.fft.fftfreq(len(z), 1/sample_rate_hz)
        power = abs(np.fft.fft(phasor))**2/len(z)**2
        assert np.isclose(power.sum(), 1, atol=1e-12)  # Parseval, unit amplitude.
        coherent_fraction = abs(phasor.mean())**2
        assert np.isclose(power[0], coherent_fraction, atol=1e-12)
        order = np.argsort(abs(frequency_hz))
        absolute_frequency_hz = abs(frequency_hz[order])
        cumulative = np.cumsum(power[order])
        bandwidths_hz = {
            str(percent): float(2*absolute_frequency_hz[
                np.searchsorted(cumulative, percent/100)])
            for percent in (50, 90, 95, 99)
        }
        indices = np.searchsorted(absolute_frequency_hz, halfwidth_hz, side="right")-1
        cumulative_curves.append(cumulative[indices])
        f_hz, density = periodogram(phasor, sample_rate_hz, window="hann",
                                   detrend=False, return_onesided=False)
        spectra.append(np.fft.fftshift(density))
        records.append(dict(source=path.name, samples=len(z),
            duration_s=len(z)/sample_rate_hz, fft_bin_hz=sample_rate_hz/len(z),
            phase_only_coherent_fraction=float(coherent_fraction),
            iq_coherent_fraction=float(abs(z.mean())**2/np.mean(abs(z)**2)),
            phase_only_power_within_plus_minus_1khz=float(power[abs(frequency_hz)<=1000].sum()),
            symmetric_full_occupied_bandwidth_hz=bandwidths_hz))

    f_hz = np.fft.fftshift(f_hz)
    density = np.mean(spectra, axis=0)  # Incoherent average; records are not joined.
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4), layout="constrained")
    # Average adjacent displayed bins to make the broad pedestal readable.
    bins = 8
    axes[0].plot(f_hz.reshape(-1, bins).mean(axis=1)/1e3,
                 10*np.log10(density.reshape(-1, bins).mean(axis=1)), lw=.8)
    axes[0].set(xlim=(-1000, 1000), ylim=(-90, -25),
                xlabel="Offset from beat reference (kHz)",
                ylabel="Phase-only spectrum (dB of total power / Hz)",
                title="Narrow carrier plus broad pedestal")
    select = abs(f_hz) <= 1200
    axes[1].plot(f_hz[select], 10*np.log10(density[select]), marker=".", lw=1)
    axes[1].set(xlim=(-1000, 1000), ylim=(-65, -20),
                xlabel="Offset from beat reference (Hz)",
                ylabel="Phase-only spectrum (dB of total power / Hz)",
                title="Central component is unresolved")
    for curve in cumulative_curves:
        axes[2].semilogx(halfwidth_hz/1e3, 100*curve, alpha=.35, lw=.8)
    axes[2].axhline(90, color=".35", ls="--", lw=.8)
    axes[2].set(xlim=(.06, 3000), ylim=(0, 102),
                xlabel="Symmetric half-width around reference (kHz)",
                ylabel="Included phase-only power (%)",
                title="90% of power spans 0.59–0.82 MHz total")
    for ax in axes:
        ax.grid(alpha=.2)
    fig.suptitle("8× gain, FRA off: measured beat line shape from ten fast I/Q records")
    fig.supxlabel("17.07 ms per record; 58.59 Hz FFT bins; Hann ENBW 87.89 Hz for spectral plots. "
                  "Finite-record coherent fraction: 13–21%.\n"
                  "Beat measurement includes reference-laser noise; no absolute optical linewidth inferred.", fontsize=9)
    for extension in ("png", "pdf"):
        fig.savefig(DIRECTORY/f"shortest_iq_lineshape.{extension}", dpi=170)
    plt.close(fig)
    result = dict(
        method="Unit phasor, no unwrapping or detrending; independent finite records.",
        bandwidth_definition="Smallest symmetric interval about zero containing the stated total phase-only power; full width, not FWHM.",
        limitations="Measured beat only. 17 ms records do not establish long-term carrier linewidth. No receiver response correction.",
        records=records)
    (DIRECTORY/"shortest_iq_lineshape.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
