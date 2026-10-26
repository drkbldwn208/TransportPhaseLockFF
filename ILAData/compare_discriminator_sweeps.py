"""Compare measured loop return ratios and a conditional 4x -> 8x prediction.

User confirms unchanged analog settings for the three sweeps. FPGA metadata
records 2x, 4x, 4x gain; the new passive I/Q captures used 8x. The prediction
assumes a linear, unchanged plant and is not an 8x FRA measurement.
"""
from pathlib import Path
import hashlib
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/compare_fra_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from analyze_discriminator_fra import crossover

DIRECTORY = Path(__file__).resolve().parent / "10-13FRA/Discriminator"


def load_sweep(stamp):
    path = DIRECTORY / f"laser_loop_20261014_{stamp}.csv"
    data = pd.read_csv(path)
    f_hz = data.frequency_hz.to_numpy()
    error = data.error_re.to_numpy()+1j*data.error_im.to_numpy()
    drive = data.drive_re.to_numpy()+1j*data.drive_im.to_numpy()
    loop = -error/drive
    reliable = data.reliable.to_numpy(bool)
    assert np.all(np.diff(f_hz) > 0) and np.allclose(loop, data.loop_re+1j*data.loop_im)
    assert not data.clipped.any()
    assert data.tracking_coefficient.nunique() == 1
    band = reliable & (f_hz >= 4000) & (f_hz < 100000)
    report = dict(source=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        gain_relative_to_stage3=float(data.tracking_coefficient.iloc[0]/104858),
        points=len(data), reliable_points=int(reliable.sum()),
        probe_amplitude_codes=int(data.amplitude_codes.iloc[0]),
        median_integration_s=float(data.measure_s.median()),
        iir_enabled=bool(int(data.iir_control_word.iloc[0]) & 1),
        rejected_clipped_blocks=int(data.clipped_repeats.sum()),
        dac_clip_samples_all_attempts=int(data.dac_clip_samples.sum()),
        detector_saturated_samples_all_attempts=int(data.detector_saturated_samples.sum()),
        accepted_clipped_points=int(data.clipped.sum()),
        measured_response=crossover(f_hz[band], loop[band]))
    return dict(data=data, f_hz=f_hz, loop=loop, reliable=reliable, band=band, report=report)


def main():
    sweeps = [load_sweep(stamp) for stamp in ("050122", "053034", "053953")]
    latest = sweeps[-1]
    band = latest["band"]
    predicted = crossover(latest["f_hz"][band], 2*latest["loop"][band])
    compare_band = (latest["f_hz"] > 10000) & (latest["f_hz"] < 70000)
    for s in sweeps:
        compare_band &= s["reliable"]
    ratio = sweeps[1]["loop"][compare_band]/sweeps[0]["loop"][compare_band]
    gain_increase_db = float(np.median(20*np.log10(abs(ratio))))
    report = dict(conditions="User confirms analog settings unchanged throughout; all saved sweeps have IIR bypassed.",
        measured=[s["report"] for s in sweeps],
        conditional_8x_prediction=predicted,
        median_measured_2x_to_4x_gain_increase_db=gain_increase_db,
        ideal_2x_to_4x_gain_increase_db=float(20*np.log10(2)),
        limitations=["Only aggregate CSVs supplied, so individual repeats cannot be re-examined.",
                     "No saved 8x FRA exists in this comparison; that curve is a conditional prediction.",
                     "Measured 2x -> 4x increase differs from ideal scaling, limiting extrapolation accuracy.",
                     "Phase margins are local unity-gain estimates, not proof of global closed-loop stability.",
                     "Clipped attempts were discarded; retained responses may describe only quieter intervals.",
                     "Low-frequency ratios with residual drive below noise are excluded."])
    (DIRECTORY/"discriminator_sweep_comparison.json").write_text(json.dumps(report, indent=2)+"\n")

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, layout="constrained")
    colors = ("#687580", "#1769aa", "#268477")
    for n, (s, color) in enumerate(zip(sweeps, colors)):
        f_hz, loop, reliable = s["f_hz"], s["loop"], s["reliable"]
        phase = np.angle(loop, deg=True)
        phase = np.where(phase > 0, phase-360, phase)
        values = (20*np.log10(abs(loop)), phase, 20*np.log10(abs(1/(1+loop))))
        label = f'{s["report"]["gain_relative_to_stage3"]:g}× measured, {s["report"]["source"][-10:-4]}'
        for ax, y in zip(axes, values):
            ax.semilogx(f_hz, np.where(reliable, y, np.nan), ".-", color=color, lw=1.2, ms=4, label=label)
            ax.semilogx(f_hz[~reliable], y[~reliable], "x", color=color, alpha=.3, ms=3)
    f_hz = latest["f_hz"][band]
    loop = 2*latest["loop"][band]
    axes[0].semilogx(f_hz, 20*np.log10(abs(loop)), "--", color="#b64c26", label="8× predicted from last 4× sweep")
    axes[2].semilogx(f_hz, 20*np.log10(abs(1/(1+loop))), "--", color="#b64c26")
    for ax in axes:
        ax.axvline(predicted["crossover_hz"], color="#b64c26", ls=":", alpha=.5)
        ax.axvspan(60000, 70000, color="#b64c26", alpha=.07)
        ax.grid(alpha=.2, which="both")
    for ax in (axes[0], axes[2]):
        ax.axhline(0, color=".4", ls=":", lw=1)
    axes[1].axhline(-180, color=".4", ls=":", lw=1)
    axes[0].set(ylabel="Loop gain (dB)", ylim=(-35, 35), title="Measured crossover: 32.2 kHz at 2×; 44.7–44.9 kHz at 4×")
    axes[0].legend(fontsize=8, loc="lower left")
    axes[1].set(ylabel="Loop phase (deg)", ylim=(-230, -95), title="Measured local phase margin: 28.3° at 2×; 22.5–23.6° at 4×")
    axes[2].set(ylabel="Sensitivity |1/(1+L)| (dB)", ylim=(-30, 15), xlabel="Test frequency (Hz)",
                xlim=(4000, 200000), title="Conditional 8× prediction: ~63 kHz crossover, ~14° margin, +12 dB sensitivity near 67 kHz")
    fig.suptitle("Repeated FRA measurements support a poorly damped response", fontsize=13)
    fig.supxlabel("Dashed orange is a prediction, not an 8× measurement. Shading marks the ~65 kHz I/Q noise feature.\n"
                  "Faint crosses fail repeat/SNR criteria. Retained phasors exclude clipped attempts.", fontsize=9)
    for extension in ("png", "pdf"):
        fig.savefig(DIRECTORY/f"discriminator_sweep_comparison.{extension}", dpi=170)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
