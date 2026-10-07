#!/usr/bin/env python3
"""Measure ADC 224/3 tone amplitude, headroom and phase noise from a saved ILA.

Usage: python3 ILAData/analyze_laser_pll_adc.py ILAData/iladata.ila

Requires the laser PLL design's real, bypassed ADC stream (old ILA slot 11;
use --adc-slot 9 for the October 7, 2026 BD):
eight chronological signed 16-bit words per 245.76 MHz clock, low word first.
Full-scale sine peak is 32768 AXIS counts; physical ADC codes are left aligned.
Assumes a continuous capture at 1.96608 GS/s with one dominant sinusoid.
The sine-fit residual includes noise, distortion and source/clock instability.
Phase predictions use floating-point mixing/atan2 with the actual FIR taps;
they exclude RTL rounding, DAC behavior and the analog output interface.
"""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import zipfile

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal import lfilter, periodogram


ADC_RATE_HZ = 1_966_080_000.0
REFERENCE_HZ = 800_000_000.0
FULL_SCALE_COUNTS = 32768


def read_adc_counts(path, slot=11):
    """Read embedded CSV without modifying the original .ila archive."""
    if path.suffix.lower() == ".ila":
        with zipfile.ZipFile(path) as archive:
            csv_text = archive.read("waveform.csv").decode()
    else:
        csv_text = path.read_text()
    reader = csv.DictReader(io.StringIO(csv_text))
    radix = next(reader)
    column = next(k for k in radix if f"net_slot_{slot}_axis_tdata[127:0]" in k)
    if radix[column] != "HEX":
        raise ValueError(f"Export ILA slot {slot} tdata in hexadecimal radix.")
    rows = list(reader)
    prefix = column.split("tdata")[0]
    if any(row[prefix + "tvalid"] != "1" or row[prefix + "tready"] != "1"
           for row in rows):
        raise ValueError("Capture contains invalid or stalled ADC words.")
    indices = np.array([int(row["Sample in Window"]) for row in rows])
    if np.any(np.diff(indices) != 1):
        raise ValueError("Capture must contain one continuous sample window.")
    words = [int(row[column], 16) for row in rows]
    unsigned = np.array([[(word >> (16*k)) & 0xffff for k in range(8)]
                         for word in words], dtype=np.int64)
    return ((unsigned + 32768) % 65536 - 32768).ravel().astype(float)


def fit_tone(adc_counts):
    """Fit A*cos(2*pi*f*t) + B*sin(2*pi*f*t) + DC; refine the FFT peak."""
    time_s = np.arange(len(adc_counts)) / ADC_RATE_HZ
    spectrum = abs(np.fft.rfft((adc_counts-adc_counts.mean()) * np.hanning(len(time_s))))
    bin_width_hz = ADC_RATE_HZ / len(time_s)
    peak_hz = (np.argmax(spectrum[1:]) + 1) * bin_width_hz

    def fit_at_frequency(frequency_hz):
        phase_rad = 2*np.pi*frequency_hz*time_s
        matrix = np.column_stack((np.cos(phase_rad), np.sin(phase_rad), np.ones(len(time_s))))
        coefficients = np.linalg.lstsq(matrix, adc_counts, rcond=None)[0]
        model_counts = matrix @ coefficients
        return np.mean((adc_counts-model_counts)**2), coefficients, model_counts

    result = minimize_scalar(lambda f: fit_at_frequency(f)[0],
                             bounds=(max(1, peak_hz-bin_width_hz),
                                     min(ADC_RATE_HZ/2-1, peak_hz+bin_width_hz)),
                             method="bounded", options={"xatol": 0.001})
    if not result.success:
        raise RuntimeError("Tone frequency fit did not converge.")
    _, coefficients, model_counts = fit_at_frequency(result.x)
    return result.x, coefficients, model_counts


def phase_noise_model(adc_counts):
    """Apply current mixer/FIR; remove fitted phase drift before comparing gains."""
    root = Path(__file__).resolve().parents[1]
    tap_file = root / "TransportPhaseLockFF.srcs/sources_1/new/laser_pll_fir_coeffs.vh"
    entries = re.findall(r"(\d+): fir_coefficient = (-?)18'sd(\d+);", tap_file.read_text())
    if [int(tap) for tap, _, _ in entries] != list(range(32)):
        raise ValueError("Expected the current 32 FIR coefficients.")
    taps = np.array([(-1 if sign else 1)*int(value) for _, sign, value in entries])/131072
    time_s = np.arange(len(adc_counts)) / ADC_RATE_HZ
    mixed = adc_counts*np.exp(-2j*np.pi*REFERENCE_HZ*time_s)
    filtered = lfilter(taps, [1.0], mixed)[7::8]
    # Drop FIR startup and a small boundary margin; do not filter phase noise.
    phase_time_s = np.arange(len(filtered)) / (ADC_RATE_HZ/8)
    phase_time_s = phase_time_s[30:-20]
    error_rad = -np.unwrap(np.angle(filtered))[30:-20]
    drift = np.polyval(np.polyfit(phase_time_s, error_rad, 1), phase_time_s)
    residual_rad = error_rad-drift
    capture_rad = residual_rad[1:] + 64*np.diff(residual_rad)
    return phase_time_s, residual_rad, capture_rad


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--adc-slot", type=int, default=11, help="ADC 224/3 ILA slot: 9 in new BD, 11 in old captures")
    args = parser.parse_args()
    adc = read_adc_counts(args.capture, args.adc_slot)
    frequency_hz, coefficients, fit = fit_tone(adc)
    amplitude_counts = np.hypot(*coefficients[:2])
    residual = adc-fit
    phase_time_s, phase_rad, capture_rad = phase_noise_model(adc)
    tone_dbfs = 20*np.log10(amplitude_counts/FULL_SCALE_COUNTS)
    result = dict(
        capture=str(args.capture), capture_sha256=hashlib.sha256(args.capture.read_bytes()).hexdigest(),
        adc_sample_rate_hz=ADC_RATE_HZ, samples=len(adc), duration_us=len(adc)/ADC_RATE_HZ*1e6,
        fitted_tone_hz=frequency_hz, fitted_peak_counts=amplitude_counts,
        fitted_peak_fraction_full_scale=amplitude_counts/FULL_SCALE_COUNTS, tone_dbfs=tone_dbfs,
        minimum_counts=float(adc.min()), maximum_counts=float(adc.max()),
        samples_near_adc_rails=int(np.count_nonzero(abs(adc) >= 32764)),
        tone_fit_residual_rms_counts=float(np.std(residual)),
        tone_to_residual_db=float(20*np.log10(amplitude_counts/np.sqrt(2)/np.std(residual))),
        gain_db_to_minus6_dbfs=-6-tone_dbfs, gain_db_to_minus3_dbfs=-3-tone_dbfs,
        phase_only_model_rms_rad=float(np.std(phase_rad)),
        phase_only_model_pp_rad=float(np.ptp(phase_rad)),
        capture64_model_unsaturated_rms_rad=float(np.std(capture_rad)),
        capture64_model_unsaturated_pp_rad=float(np.ptp(capture_rad)),
        notes="Capture64 is a modeled setting, not read from ILA. No absolute dBm calibration. "
              "Gain targets assume linear analog scaling with unchanged RFDC settings. "
              "Tone-fit residual includes noise and distortion across the full ADC Nyquist band.")
    output = args.capture.with_name("laser_pll_adc_analysis")
    output.with_suffix(".json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))

    fig, axes = plt.subplots(3, 1, figsize=(10, 9), constrained_layout=True)
    plot_time_s = np.linspace(0, 39/ADC_RATE_HZ, 2000)
    plot_phase_rad = 2*np.pi*frequency_hz*plot_time_s
    plot_fit = coefficients[0]*np.cos(plot_phase_rad) + coefficients[1]*np.sin(plot_phase_rad) + coefficients[2]
    axes[0].plot(plot_time_s*1e9, plot_fit, label="Sine fit", alpha=0.6)
    axes[0].plot(np.arange(40)/ADC_RATE_HZ*1e9, adc[:40], ".", label="ILA samples")
    axes[0].set(xlabel="Time (ns)", ylabel="ADC AXIS counts",
                title=f"ADC 224/3: {frequency_hz/1e6:.6f} MHz, {tone_dbfs:.2f} dBFS; rails ±32768")
    axes[0].legend()
    for values, label in ((adc, "ADC spectrum"), (residual, "After subtracting fitted sine")):
        freq_hz, density = periodogram(values, fs=ADC_RATE_HZ, window="hann", scaling="density")
        dbfs_hz = 10*np.log10(np.maximum(density/(FULL_SCALE_COUNTS**2/2), 1e-30))
        axes[1].plot(freq_hz/1e6, dbfs_hz, linewidth=0.7, label=label)
    axes[1].set(xlabel="Frequency (MHz)", ylabel="PSD (dBFS/Hz)", title="Full ADC bandwidth; Hann window")
    axes[1].legend()
    axes[2].plot(phase_time_s[1:]*1e6, capture_rad/(2*np.pi)*100, linewidth=0.6,
                 label=f"Capture weight 64: {np.std(capture_rad):.3f} rad RMS")
    axes[2].plot(phase_time_s*1e6, phase_rad/(2*np.pi)*100, linewidth=0.6,
                 label=f"Phase only: {np.std(phase_rad)*1e3:.2f} mrad RMS")
    axes[2].set(xlabel="Time (µs)", ylabel="Residual (% of full 2π span)",
                title="Floating-point detector prediction from ILA; linear drift removed; before clipping")
    axes[2].legend()
    for ax in axes:
        ax.grid(alpha=0.25)
    fig.savefig(output.with_suffix(".png"), dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
