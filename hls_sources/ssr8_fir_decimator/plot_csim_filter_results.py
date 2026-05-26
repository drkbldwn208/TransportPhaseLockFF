#!/usr/bin/env python3
"""Plot C-simulation output from the SSR8 FIR decimator testbench.

Run after Vitis/Vivado HLS C simulation:

    vitis_hls -f run_hls.tcl
    python3 plot_csim_filter_results.py

The script searches for C-sim CSV files in the current directory and in the
usual HLS csim/build folder. It creates a PNG with:

1. measured frequency response from the swept C-sim run,
2. passband zoom,
3. optional time-domain smoke-test plot when csim_filter_results.csv exists.
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt
import numpy as np


DEFAULT_TIME_CSV_NAMES = (
    Path("csim_filter_results.csv"),
    Path("ssr8_fir_decimator_prj/solution1/csim/build/csim_filter_results.csv"),
)

DEFAULT_RESPONSE_CSV_NAMES = (
    Path("csim_frequency_response.csv"),
    Path("ssr8_fir_decimator_prj/solution1/csim/build/csim_frequency_response.csv"),
)


def find_csv(explicit: str | None, names: tuple[Path, ...], filename: str) -> Path | None:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    for path in names:
        if path.exists():
            return path

    matches = sorted(Path(".").rglob(filename))
    if matches:
        return matches[-1]

    return None


def read_frequency_response(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    freq_hz: list[float] = []
    gain_db: list[float] = []
    output_amplitude: list[float] = []

    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            freq_hz.append(float(row["freq_hz"]))
            gain_db.append(float(row["gain_db"]))
            output_amplitude.append(float(row["output_amplitude"]))

    return (
        np.asarray(freq_hz),
        np.asarray(gain_db),
        np.asarray(output_amplitude),
    )


def read_results(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    beats: list[int] = []
    input_newest: list[int] = []
    output_valid: list[int] = []
    output_sample: list[int] = []

    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            beats.append(int(row["beat"]))
            input_newest.append(int(row["input_newest"]))
            output_valid.append(int(row["output_valid"]))
            output_sample.append(int(row["output_sample"]))

    return (
        np.asarray(beats),
        np.asarray(input_newest),
        np.asarray(output_valid, dtype=bool),
        np.asarray(output_sample),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response-csv", help="Path to csim_frequency_response.csv")
    parser.add_argument("--time-csv", help="Path to csim_filter_results.csv")
    parser.add_argument("--out", default="csim_frequency_response.png", help="Output PNG path")
    parser.add_argument("--fs-in", type=float, default=1966.08e6, help="Input sample rate in Hz")
    parser.add_argument("--time-samples", type=int, default=256, help="Samples to show in time plot")
    parser.add_argument("--passband-mhz", type=float, default=80.0, help="Passband zoom limit")
    args = parser.parse_args()

    response_csv = find_csv(
        args.response_csv,
        DEFAULT_RESPONSE_CSV_NAMES,
        "csim_frequency_response.csv",
    )
    if response_csv is None:
        raise FileNotFoundError(
            "Could not find csim_frequency_response.csv. Run `vitis_hls -f run_hls.tcl` first."
        )

    time_csv = find_csv(args.time_csv, DEFAULT_TIME_CSV_NAMES, "csim_filter_results.csv")
    freq_hz, gain_db, output_amplitude = read_frequency_response(response_csv)

    rows = 3 if time_csv is not None else 2
    fig, axes = plt.subplots(rows, 1, figsize=(11, 4 + 2.4 * rows), constrained_layout=True)
    ax_full = axes[0]
    ax_zoom = axes[1]

    ax_full.plot(freq_hz / 1e6, gain_db, marker=".", markersize=2.5, linewidth=1.0)
    ax_full.axvline(122.88, color="tab:red", linestyle="--", linewidth=1.0, label="output Nyquist")
    ax_full.set_title("Measured C-Sim Frequency Response")
    ax_full.set_xlabel("input frequency (MHz)")
    ax_full.set_ylabel("gain (dB)")
    ax_full.set_xlim(0, args.fs_in / 2.0 / 1e6)
    ax_full.set_ylim(max(-160, float(np.nanmin(gain_db)) - 5), 5)
    ax_full.grid(True, alpha=0.3)
    ax_full.legend(loc="best")

    passband = freq_hz <= args.passband_mhz * 1e6
    ax_zoom.plot(freq_hz[passband] / 1e6, gain_db[passband], marker=".", markersize=3, linewidth=1.1)
    ax_zoom.set_title(f"Passband Zoom: 0 to {args.passband_mhz:g} MHz")
    ax_zoom.set_xlabel("input frequency (MHz)")
    ax_zoom.set_ylabel("gain (dB)")
    ax_zoom.set_xlim(0, args.passband_mhz)
    ax_zoom.grid(True, alpha=0.3)

    if time_csv is not None:
        beats, input_newest, output_valid, output_sample = read_results(time_csv)
        valid_beats = beats[output_valid]
        valid_output = output_sample[output_valid]

        n_time = min(args.time_samples, len(valid_output))
        n_input_time = min(args.time_samples, len(beats))
        input_time_us = beats / (args.fs_in / 8.0) * 1e6
        output_time_us = valid_beats / (args.fs_in / 8.0) * 1e6

        ax_time = axes[2]
        ax_time.plot(
            input_time_us[:n_input_time],
            input_newest[:n_input_time],
            label="input newest lane",
            linewidth=1.0,
            alpha=0.65,
        )
        ax_time.step(
            output_time_us[:n_time],
            valid_output[:n_time],
            where="post",
            label="decimated FIR output",
            linewidth=1.2,
        )
        ax_time.set_title("Two-Tone Smoke Test Time Trace")
        ax_time.set_xlabel("time (us)")
        ax_time.set_ylabel("sample code")
        ax_time.grid(True, alpha=0.3)
        ax_time.legend(loc="best")

    fig.suptitle(f"Frequency response source: {response_csv}", fontsize=10)
    fig.savefig(args.out, dpi=160)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
