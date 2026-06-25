#!/usr/bin/env python3
"""Plot the averaged 64-bit ADC bus captured by the Vivado ILA.

The ADC bus is treated as four signed 16-bit samples packed into one 64-bit
word.  This script sign-converts each lane, averages the four samples, and
plots that average versus ILA sample time.
"""

import argparse
import csv
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt
import numpy as np

from plot_cordic_tdata import (
    low_pass_first_order,
    plot_spectrum,
    plot_time_series,
    print_strongest_spectral_bins,
    signed16,
    single_sided_amplitude_spectrum,
)


CSV_PATH = Path("iladata.csv")
SAMPLE_COLUMN = "Sample in Window"

# In the current CSV this probe is the 64-bit ADC bus.  It carries the same
# values as net_slot_7_axis_tdata[63:0] for the inspected capture.
ADC_BUS_COLUMN = "design_1_i/system_ila_0/inst/probe4_1[63:0]"


def average_adc_word(raw_u64):
    """Average four signed 16-bit ADC samples packed into one 64-bit word."""
    lanes = [
        signed16((raw_u64 >> 0) & 0xFFFF),
        signed16((raw_u64 >> 16) & 0xFFFF),
        signed16((raw_u64 >> 32) & 0xFFFF),
        signed16((raw_u64 >> 48) & 0xFFFF),
    ]
    return sum(lanes) / len(lanes)


def read_adc_average(csv_path, adc_bus_column):
    """Return (sample_index, averaged_adc_count) arrays from a Vivado ILA CSV."""
    sample_index = []
    adc_average = []

    with Path(csv_path).open(newline="") as f:
        reader = csv.DictReader(f)
        next(reader)  # Vivado radix row, not a data sample.

        for row in reader:
            sample_index.append(int(row[SAMPLE_COLUMN]))
            adc_average.append(average_adc_word(int(row[adc_bus_column], 16)))

    return sample_index, adc_average


def main():
    parser = argparse.ArgumentParser(
        description="Plot the average of four signed 16-bit ADC samples in a 64-bit bus."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=CSV_PATH,
        help="Vivado ILA CSV file to read (default: iladata.csv)",
    )
    parser.add_argument(
        "--column",
        default=ADC_BUS_COLUMN,
        help="CSV column containing the packed 64-bit ADC bus.",
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

    sample_index, adc_average = read_adc_average(args.csv_path, args.column)
    y_values = np.array(adc_average, dtype=float)
    y_label = "averaged ADC count"
    title = "Averaged ADC bus versus time"

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
