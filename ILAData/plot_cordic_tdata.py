#!/usr/bin/env python3
"""Plot the CORDIC AXI stream phase captured by the Vivado ILA.

The current design configures cordic_0 as Xilinx CORDIC Arc_Tan with
Phase_Format = Radians and Output_Width = 16.  That phase output is signed
Q3.13 radians, so 0x2000 means +1.0 rad.  If the ILA sample clock rate is
known, pass it with --sample-rate-hz to plot real time in seconds; otherwise
the x-axis is in ILA sample clock ticks.
"""

import argparse
import csv
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt
import numpy as np


CSV_PATH = Path("iladata.csv")

# Vivado labels the interface as cordic_0_M_AXIS_DOUT, but the raw tdata column
# is exported under its ILA net slot name.
CORDIC_TDATA_COLUMN = "design_1_i/system_ila_0/inst/net_slot_0_axis_tdata[15:0]"
SAMPLE_COLUMN = "Sample in Window"
CORDIC_PHASE_TOTAL_BITS = 16
CORDIC_PHASE_INTEGER_BITS = 3  # Includes the sign bit.
CORDIC_PHASE_FRACTIONAL_BITS = CORDIC_PHASE_TOTAL_BITS - CORDIC_PHASE_INTEGER_BITS


def read_cordic_samples(csv_path):
    """Return (sample_index, cordic_tdata) arrays from a Vivado ILA CSV file."""
    csv_path = Path(csv_path)
    sample_index = []
    cordic_tdata = []

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        next(reader)  # Vivado radix row, not a data sample.

        for row in reader:
            sample_index.append(int(row[SAMPLE_COLUMN]))
            cordic_tdata.append(int(row[CORDIC_TDATA_COLUMN], 16))

    return sample_index, cordic_tdata


def cordic_phase_radians(raw_u16):
    """Convert CORDIC Q3.13 phase from unsigned 16-bit storage to radians.

    This is a signed 16-bit fixed-point phase with 3 integer bits including the
    sign bit and 13 fractional bits.  For example, 0x2000 is +1 rad.
    """
    signed_value = raw_u16 - 0x10000 if raw_u16 & 0x8000 else raw_u16
    return signed_value / (1 << CORDIC_PHASE_FRACTIONAL_BITS)


def signed16(raw_u16):
    """Interpret the raw ILA word as a signed 16-bit integer."""
    return raw_u16 - 0x10000 if raw_u16 & 0x8000 else raw_u16


def low_pass_first_order(values, cutoff, sample_rate):
    """Apply a causal first-order low-pass filter with the given cutoff."""
    if cutoff <= 0:
        raise ValueError("Low-pass cutoff must be positive.")
    if cutoff >= 0.5 * sample_rate:
        raise ValueError("Low-pass cutoff must be below the Nyquist frequency.")

    alpha = 1.0 - np.exp(-2.0 * np.pi * cutoff / sample_rate)
    filtered = np.empty_like(values, dtype=float)
    filtered[0] = values[0]

    for n in range(1, len(values)):
        filtered[n] = filtered[n - 1] + alpha * (values[n] - filtered[n - 1])

    return filtered


def plot_time_series(ax, time_axis, y_values, x_label, y_label, title):
    ax.plot(time_axis, y_values, linewidth=1.0)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)


def single_sided_amplitude_spectrum(y_values, sample_rate):
    """Return frequency and single-sided amplitude spectrum after removing DC."""
    signal = y_values - np.mean(y_values)
    window = np.hanning(len(signal))
    coherent_gain = np.mean(window)
    spectrum = np.fft.rfft(signal * window)
    frequency = np.fft.rfftfreq(len(signal), d=1.0 / sample_rate)
    amplitude = 2.0 * np.abs(spectrum) / (len(signal) * coherent_gain)
    return frequency, amplitude


def print_strongest_spectral_bins(frequency, amplitude, frequency_units, count=5):
    """Print the largest non-DC FFT bins as a quick spectral summary."""
    if len(frequency) <= 1:
        return

    strongest_indices = np.argsort(amplitude[1:])[-count:][::-1] + 1
    print("Strongest non-DC spectral bins:")
    for index in strongest_indices:
        print(
            f"  {frequency[index]:.6g} {frequency_units}: "
            f"amplitude {amplitude[index]:.6g}"
        )


def plot_spectrum(ax, frequency, amplitude, frequency_label, y_label):
    """Plot the single-sided amplitude spectrum."""
    ax.plot(frequency, amplitude, linewidth=1.0)
    ax.set_xlabel(frequency_label)
    ax.set_ylabel(f"Amplitude ({y_label})")
    ax.set_title("Single-sided amplitude spectrum")
    ax.grid(True, alpha=0.3)


def main():
    parser = argparse.ArgumentParser(
        description="Plot cordic_0_m_axis_tdata versus ILA sample time."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=CSV_PATH,
        help="Vivado ILA CSV file to read (default: iladata.csv)",
    )
    parser.add_argument(
        "--sample-rate-hz",
        type=float,
        default=None,
        help="ILA sample clock rate in Hz. If omitted, x-axis is sample clocks.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional PNG file to write. If omitted, no PNG is saved.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Plot raw signed 16-bit CORDIC output counts instead of radians.",
    )
    parser.add_argument(
        "--low-pass-cutoff",
        type=float,
        default=None,
        help=(
            "Apply a first-order low-pass filter before plotting. Units are Hz "
            "if --sample-rate-hz is given, otherwise cycles per ILA sample clock."
        ),
    )
    parser.add_argument(
        "--spectrum",
        action="store_true",
        help=(
            "Also plot the single-sided FFT amplitude spectrum of the displayed "
            "signal and print the strongest non-DC FFT bins."
        ),
    )
    args = parser.parse_args()

    sample_index, cordic_tdata = read_cordic_samples(args.csv_path)
    if args.raw:
        y_values = np.array([signed16(raw_u16) for raw_u16 in cordic_tdata], dtype=float)
        y_label = "phase word, signed counts"
        title = "CORDIC phase word versus time"
    else:
        y_values = np.array(
            [cordic_phase_radians(raw_u16) for raw_u16 in cordic_tdata],
            dtype=float,
        )
        y_label = "phase, rad"
        title = "CORDIC phase versus time"

    if args.sample_rate_hz:
        sample_rate = args.sample_rate_hz
        time_axis = np.array(sample_index, dtype=float) / sample_rate
        x_label = "Time (s)"
        frequency_label = "Frequency (Hz)"
        frequency_units = "Hz"
    else:
        sample_rate = 1.0
        time_axis = np.array(sample_index, dtype=float)
        x_label = "Time (ILA sample clocks)"
        frequency_label = "Frequency (cycles per ILA sample clock)"
        frequency_units = "cycles/sample"

    if args.low_pass_cutoff is not None:
        y_values = low_pass_first_order(y_values, args.low_pass_cutoff, sample_rate)
        y_label = f"filtered {y_label}"
        title = f"{title}, low-pass cutoff = {args.low_pass_cutoff:g} {frequency_units}"

    print(f"Average {y_label}: {np.mean(y_values):.9g}")

    if args.spectrum:
        frequency, amplitude = single_sided_amplitude_spectrum(y_values, sample_rate)
        print_strongest_spectral_bins(frequency, amplitude, frequency_units)

        fig, axes = plt.subplots(2, 1, constrained_layout=True)
        plot_time_series(axes[0], time_axis, y_values, x_label, y_label, title)
        plot_spectrum(axes[1], frequency, amplitude, frequency_label, y_label)
    else:
        fig, ax = plt.subplots()
        plot_time_series(ax, time_axis, y_values, x_label, y_label, title)
        fig.tight_layout()

    if args.output:
        fig.savefig(args.output, dpi=150)
        print(f"Saved {args.output}")

    plt.show()


if __name__ == "__main__":
    main()
