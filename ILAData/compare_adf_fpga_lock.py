"""Compare measured RF beat sidebands with FPGA and ADF4108 feedback.

Carrier frequencies differ (800 MHz / 1 GHz), so align each displayed carrier
peak. Preserve native-RBW line heights; divide by RBW only for a separate,
approximate broadband comparison. Positive-peak display buckets are NOT a
calibrated PSD, and cannot be integrated to obtain RMS phase noise.
"""
from pathlib import Path
import hashlib
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/adf_fpga_matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
BLUE, ORANGE, GREEN, GRAY = "#1769aa", "#cb542a", "#248570", "#858585"


def load_trace(filename):
    path = ROOT / filename
    lines = path.read_text().splitlines()
    rows = lines[lines.index("BEGIN") + 1:lines.index("END")]
    frequency_hz, power_dbm = np.array([
        [float(value) for value in row.split(",")[:2]] for row in rows if row
    ]).T
    assert np.all(np.diff(frequency_hz) > 0)
    assert np.all(np.isfinite(power_dbm))

    def header(key):
        return next(line.removeprefix("!").strip()[len(key):].strip()
                    for line in lines if line.removeprefix("!").strip().startswith(key))

    peak = np.argmax(power_dbm)
    metadata = dict(
        file=filename, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        analyzer_timestamp=header("TIMESTAMP"), timezone=header("TIMEZONE"),
        center_frequency_hz=float(header("CenterFreq")),
        span_hz=float(header("SpanFreq")), rbw_hz=float(header("ResolutionBW")),
        vbw_hz=float(header("VideoBW")), attenuation_db=float(header("RF Attenuation")),
        detector=header("Detector"), averaging=header("TraceAvgCount"),
        incomplete_sweep_warning=any("measurement incomplete" in line for line in lines),
        carrier_display_frequency_hz=float(frequency_hz[peak]),
        carrier_display_power_dbm=float(power_dbm[peak]),
        display_spacing_hz=float(np.median(np.diff(frequency_hz))),
    )
    # Instrument input attenuation is already calibrated into its dBm values.
    # Do NOT add or subtract the 0 / 20 dB attenuation settings here.
    offset_hz = frequency_hz - frequency_hz[peak]
    relative_dbc = power_dbm - power_dbm[peak]
    density_proxy = relative_dbc - 10 * np.log10(metadata["rbw_hz"])
    # An unresolved carrier is tone power, not a broadband density measurement.
    density_proxy[abs(offset_hz) < 2 * metadata["display_spacing_hz"]] = np.nan
    return dict(metadata=metadata, offset_hz=offset_hz, power_dbm=power_dbm,
                relative_dbc=relative_dbc, density_proxy=density_proxy)


def strongest_lines(trace, low_hz, high_hz):
    """Return the strongest displayed point in each of two symmetric windows."""
    x, y = trace["offset_hz"], trace["relative_dbc"]
    result = []
    for sign in (-1, 1):
        indices = np.flatnonzero((sign * x >= low_hz) & (sign * x < high_hz))
        index = indices[np.argmax(y[indices])]
        result.append(dict(offset_hz=float(x[index]), level_dbc=float(y[index])))
    return result


def median_bands(trace):
    """Robust displayed background proxy, NOT band-integrated phase noise."""
    records = []
    for low_hz, high_hz in [(1000, 10000), (10000, 20000), (30000, 60000),
                             (40000, 60000), (60000, 70000)]:
        selected = (abs(trace["offset_hz"]) >= low_hz) & (abs(trace["offset_hz"]) < high_hz)
        records.append(dict(low_hz=low_hz, high_hz=high_hz, points=int(selected.sum()),
            median_broadband_proxy_db=float(np.median(trace["density_proxy"][selected]))))
    return records


def draw(ax, trace, field, label, color, **kwargs):
    ax.plot(trace["offset_hz"] / 1000, trace[field], color=color,
            label=label, **kwargs)


def main():
    fpga = load_trace("File_0BEST.csv")
    adf = load_trace("File_0_ADF4108_Loop.csv")
    adf_wide = load_trace("File_01_ADF4108_Loop.csv")
    older_fpga = load_trace("File_04xW.csv")
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 11})
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), layout="constrained")
    for ax in axes[0]:
        draw(ax, fpga, "relative_dbc", "FPGA 8×, last night · RBW 10 Hz", BLUE,
             lw=1.2, marker=".", ms=3)
        draw(ax, adf, "relative_dbc", "ADF4108, new · RBW 3 Hz", ORANGE,
             lw=1.1, marker=".", ms=3)
        ax.set(ylabel="Level relative to displayed carrier (dBc)", ylim=(-55, 3))
    axes[0, 0].set(xlim=(-12, 12), title="Close-in lines: ADF has stronger ±5 kHz features")
    axes[0, 1].set(xlim=(-72, 72), title="Shared 47–53 kHz line family: stronger with FPGA")

    for ax in axes[1]:
        draw(ax, fpga, "density_proxy", "FPGA 8× · coverage only ±72 kHz", BLUE, lw=1.1)
        draw(ax, adf, "density_proxy", "ADF4108 · RBW 3 Hz", ORANGE, lw=1.0)
        draw(ax, adf_wide, "density_proxy", "ADF4108 wide · RBW 30 Hz", GREEN,
             lw=1.2, marker=".", ms=2.8)
        ax.set(ylabel="Carrier-relative level − 10 log₁₀(RBW/Hz)", ylim=(-64, -20))
    axes[1, 0].set(xlim=(-72, 72), title="Approximate broadband comparison; not phase PSD")
    draw(axes[1, 1], older_fpga, "density_proxy", "Older FPGA 4× · different settings",
         GRAY, lw=1, ls="--", alpha=.8)
    axes[1, 1].set(xlim=(-560, 560), title="Wide scan: broad feature around |offset| ≈ 350 kHz")
    axes[1, 1].axvspan(-72, 72, color=BLUE, alpha=.06)
    axes[1, 1].text(.5, .04, "No wide-span RF scan of last night's 8× lock",
                   ha="center", transform=axes[1, 1].transAxes, fontsize=9)
    for ax in axes.flat:
        ax.set_xlabel("Offset from displayed carrier peak (kHz)")
        ax.grid(alpha=.22)
        ax.legend(fontsize=8, loc="lower left" if ax is axes[1, 0] else "best")
    fig.suptitle("FPGA versus ADF4108 optical phase lock\n"
        "Carriers aligned independently: 800 MHz / 1 GHz. Analog filter settings unchanged; gains believed unchanged.",
        fontsize=12)
    fig.supxlabel("Positive-peak detection, one sweep, incomplete-sweep flags. "
        "Native line heights and RBW-normalized backgrounds have different meanings.", fontsize=9)
    fig.savefig(ROOT / "adf_fpga_lock_comparison.png", dpi=180)
    fig.savefig(ROOT / "adf_fpga_lock_comparison.pdf")
    plt.close(fig)

    # Calculate detector slopes from the same approximate 2 Vpp output span.
    # ADF K_phi = Icp*Z/(2*pi*N), with Icp*Z = 1 V for +/-1 V rails.
    output_span_v = 2.0
    adf_divisor = 80
    adf_slope_v_per_rad = (output_span_v / 2) / (2 * np.pi * adf_divisor)
    fpga_slope_v_per_rad = output_span_v / (2 * np.pi * (160 / 8))
    delay_s = 105.540e-9  # Stage 4 fabric + FIR, excludes converters / analog.
    summary = dict(
        operating_point="User confirmed FPGA 8x (/20), ADF N=80 and Icp=2.5 mA; "
                        "analog filters unchanged and gains believed unchanged.",
        traces=[trace["metadata"] for trace in (fpga, adf, adf_wide, older_fpga)],
        native_line_comparison={label: {
            "around_5khz": strongest_lines(trace, 4500, 5500),
            "family_45_54khz": strongest_lines(trace, 45000, 54000),
            "median_broadband_proxies": median_bands(trace),
        } for label, trace in [("FPGA8x", fpga), ("ADF4108", adf)]},
        ideal_detector_comparison=dict(
            assumed_span_vpp=output_span_v,
            adf_slope_v_per_rad=adf_slope_v_per_rad,
            fpga_8x_slope_v_per_rad=fpga_slope_v_per_rad,
            fpga_vs_adf_gain_db=float(20 * np.log10(fpga_slope_v_per_rad / adf_slope_v_per_rad)),
            fpga_8x_centered_headroom_turns=10,
            fpga_8x_voltage_per_beat_cycle_v=0.1,
            fpga_stage4_fabric_delay_ns=delay_s * 1e9,
            fabric_delay_lag_deg={str(f): 360 * f * delay_s for f in (50000, 350000, 1000000)},
            caveat="Equal full-current/voltage output spans and a linear ADF output amplifier "
                   "are assumed; the complete detector transfer functions are unmeasured."),
        limitations=[
            "Positive-peak detector / unequal RBWs and bucket widths bias random-noise levels.",
            "The displayed point spacing is much wider than the RBW: do not integrate plotted lines as a PSD.",
            "Broadband normalization uses nominal RBW, not calibrated ENBW or detector corrections.",
            "Carrier normalization removes a scalar level difference but not AM, carrier depletion, or receiver changes.",
            "All files carry the analyzer's incomplete-sweep warning.",
            "Last night's FPGA RF spectrum ends near +/-72 kHz; older 4x wide spectrum is context only.",
            "RF sidebands contain both AM and PM, including large-modulation effects; no RMS phase is inferred.",
            "Spectral bumps are not a measurement of unity-gain crossover or phase margin.",
            "Unchanged analog controller settings do not imply matched discriminator slope or total loop gain.",
        ],
    )
    (ROOT / "adf_fpga_lock_comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"lines": summary["native_line_comparison"],
                      "detectors": summary["ideal_detector_comparison"]}, indent=2))


if __name__ == "__main__":
    main()
