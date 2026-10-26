"""Recompute the latest laser-loop response, loopback delays and detector model.

Offline only: no FPGA/helper imports or hardware writes. Use reliable points,
preserve complex phasors, and fit phase with a free intercept. Dependencies:
NumPy, pandas and Matplotlib. All outputs are relative to this file.
"""
from pathlib import Path
import json
import os
import numpy as np
import pandas as pd
from discriminator_model import (GAIN_CODES_PER_RAD, POST_IQ_CLOCKS,
                                 POST_IQ_DELAY_S, electronics_response)
from analyze_phase_noise import analyze_phase_noise

ROOT = Path(__file__).resolve().parent


def flags(column):
    return column.astype(str).str.lower().eq("true").to_numpy()


def phasor(table, prefix):
    return table[prefix+"_re"].to_numpy() + 1j*table[prefix+"_im"].to_numpy()


def crossing(frequency_hz, loop):
    gain_db = 20*np.log10(abs(loop))
    phase_deg = np.rad2deg(np.unwrap(np.angle(loop)))
    phase_deg -= 360*round((np.median(phase_deg)+150)/360)
    index = np.flatnonzero((gain_db[:-1] >= 0) & (gain_db[1:] < 0))
    assert len(index) == 1, "Expected one downward crossing in the selected band."
    k = index[0]
    weight = -gain_db[k]/(gain_db[k+1]-gain_db[k])
    frequency = np.exp(np.log(frequency_hz[k]) + weight*np.log(frequency_hz[k+1]/frequency_hz[k]))
    phase = phase_deg[k] + weight*(phase_deg[k+1]-phase_deg[k])
    sensitivity_db = 20*np.log10(abs(1/(1+loop)))
    peak = np.argmax(sensitivity_db)
    return dict(crossover_hz=float(frequency), phase_at_crossover_deg=float(phase),
                local_phase_margin_deg=float(180+phase),
                peak_sensitivity_db=float(sensitivity_db[peak]),
                peak_sensitivity_frequency_hz=float(frequency_hz[peak]))


def closed_loop(path):
    data = pd.read_csv(path)
    frequency_hz = data.frequency_hz.to_numpy()
    error, drive = phasor(data, "error"), phasor(data, "drive")
    loop = -error/drive
    assert np.all(np.diff(frequency_hz) > 0)
    assert np.allclose(loop, phasor(data, "loop"))
    assert np.allclose(drive-error, phasor(data, "injection"))
    assert np.allclose(drive/(drive-error), phasor(data, "sensitivity"))
    reliable = flags(data.reliable) & ~flags(data.clipped)
    band = reliable & (frequency_hz >= 4000) & (frequency_hz < 100000)
    result = dict(file=str(path.relative_to(ROOT)), points=len(data),
                  reliable_points=int(reliable.sum()),
                  tracking_gain_relative_to_stage3=float(data.tracking_coefficient.iloc[0]/104858),
                  iir_enabled=bool(int(data.iir_control_word.iloc[0]) & 1),
                  rejected_clipped_blocks=int(data.clipped_repeats.sum()),
                  measured_response=crossing(frequency_hz[band], loop[band]))
    return result


def loopback(path):
    data = pd.read_csv(path)
    frequency_hz = data.frequency_hz.to_numpy()
    h = data.h_real.to_numpy() + 1j*data.h_imag.to_numpy()
    assert np.all(np.diff(frequency_hz) > 0)
    assert np.allclose(data.magnitude_db, 20*np.log10(abs(h)))
    assert np.allclose(data.phase_deg, np.angle(h, deg=True))
    blocks = pd.read_csv(path.with_name(path.stem+"_blocks.csv"))
    for frequency, group in blocks.groupby("frequency_hz"):
        index = np.flatnonzero(np.isclose(frequency_hz, frequency, rtol=0, atol=1e-8))
        assert len(index) == 1
        k = index[0]
        values = group.h_real.to_numpy() + 1j*group.h_imag.to_numpy()
        sem = np.std(values, ddof=1)/np.sqrt(len(values))
        assert len(values) == data.repeats.iloc[k]
        assert np.allclose(values.mean(), h[k], rtol=1e-10, atol=1e-12)
        assert np.isclose(sem, data.complex_sem.iloc[k], rtol=1e-9)
        assert np.isclose(abs(h[k])/sem, data.snr.iloc[k], rtol=1e-9)
    selected = flags(data.reliable) & (frequency_hz >= 10000) & (frequency_hz <= 1e6)
    f = frequency_hz[selected]
    phase_rad = np.unwrap(np.angle(h[selected]))
    sigma_rad = np.maximum(data.complex_sem.to_numpy()[selected]/abs(h[selected]), 1e-5)
    slope, intercept = np.polyfit(f, phase_rad, 1, w=1/sigma_rad)
    residual_rad = phase_rad-(slope*f+intercept)
    return dict(file=str(path.relative_to(ROOT)), points=len(data), blocks=len(blocks),
                reliable_points=int(flags(data.reliable).sum()),
                frequency_range_hz=frequency_hz[[0, -1]].tolist(),
                delay_fit_band_hz=[10000, 1e6],
                delay_s=float(-slope/(2*np.pi)), phase_intercept_deg=float(np.rad2deg(intercept)),
                phase_residual_rms_deg=float(np.rad2deg(np.sqrt(np.mean(residual_rad**2)))),
                median_low_frequency_magnitude_db=float(np.median(data.magnitude_db[frequency_hz < 1000])),
                block_averages_and_uncertainties_verified=True)


def latest_plot(path, result):
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/fra_export_mpl")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = pd.read_csv(path)
    f_hz = data.frequency_hz.to_numpy()
    loop = -phasor(data, "error")/phasor(data, "drive")
    reliable = flags(data.reliable) & ~flags(data.clipped)
    phase_deg = np.angle(loop, deg=True)
    phase_deg = np.where(phase_deg > 0, phase_deg-360, phase_deg)
    values = (20*np.log10(abs(loop)), phase_deg, 20*np.log10(abs(1/(1+loop))))
    labels = ("Loop gain (dB)", "Loop phase (deg)", "Sensitivity magnitude (dB)")
    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True, layout="constrained")
    for ax, y, label in zip(axes, values, labels):
        ax.semilogx(f_hz, np.where(reliable, y, np.nan), ".-", color="#1769aa",
                    label="Reliable measurement")
        ax.semilogx(f_hz[~reliable], y[~reliable], "x", color=".7", ms=4,
                    label="Fails saved quality criteria")
        ax.axvline(result["crossover_hz"], color=".4", linestyle=":")
        ax.set_ylabel(label)
        ax.grid(alpha=.2, which="both")
    axes[0].axhline(0, color=".5", linestyle=":")
    axes[0].legend(fontsize=9)
    axes[0].set_ylim(-40, 40)
    axes[1].axhline(-180, color=".5", linestyle=":")
    axes[1].set_ylim(-240, -90)
    axes[2].axhline(0, color=".5", linestyle=":")
    axes[2].set(xlim=(4000, 200000), ylim=(-30, 12), xlabel="Modulation frequency (Hz)")
    fig.suptitle("Latest laser-loop FRA: 20261014_053953, 4× tracking gain, IIR bypassed\n"
                 f"Crossover {result['crossover_hz']/1000:.2f} kHz; "
                 f"local phase margin {result['local_phase_margin_deg']:.2f}°")
    fig.supxlabel("Measured E/U only. Full sweep retained in CSV; plot focuses on crossover.\n"
                  "Retained phasors exclude clipped attempts. No gain-extrapolation curves.", fontsize=9)
    (ROOT/"figures").mkdir(exist_ok=True)
    fig.savefig(ROOT/"figures/latest_loop.png", dpi=160)
    plt.close(fig)


def main():
    latest = ROOT/"data/closed_loop/laser_loop_20261014_053953.csv"
    report = dict(
        assumptions=["Loop margins are local estimates in the reliable 4–100 kHz band.",
                     "Interface delays include fixtures and receiver stages; no de-embedding.",
                     "Loopback calibration/settings JSON and closed-loop blocks are absent."],
        closed_loop=[closed_loop(latest)],
        loopback=[loopback(p) for p in sorted((ROOT/"data/loopback").glob("*.csv"))
                  if not p.stem.endswith("_blocks")],
    )
    target = ROOT/"results/recomputed_summary.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2)+"\n")
    # The recorded inversion cancels reference-minus-measured phase subtraction.
    data = pd.read_csv(latest)
    assert np.all(data.tracking_coefficient == 419432)
    assert np.all((data.pll_control_word.to_numpy(dtype=int) & 4) != 0)
    assert np.all((data.iir_control_word.to_numpy(dtype=int) & 1) == 0)
    fc_hz = report["closed_loop"][0]["measured_response"]["crossover_hz"]
    model = dict(kind="Assumed flat phase gain plus delay; not measured RF-PM",
        gain_codes_per_rad=GAIN_CODES_PER_RAD,
        nominal_gain_v_per_rad_for_2vpp=GAIN_CODES_PER_RAD*2/65536,
        sign="Positive E for increasing beat-minus-reference phase; analog sign separate",
        post_iq_clocks=POST_IQ_CLOCKS, post_iq_delay_s=POST_IQ_DELAY_S,
        components_clocks=dict(cordic=7, phase_subtraction=1, tracking=6, handoff=1),
        input_units="rad", output_units="DAC codes", fixtures=[],
        assumptions=["Recorded 4x tracking slope, fixed gain, no clipping, IIR bypassed.",
                     "90 MHz envelope delay is used as a proxy for phase-response delay.",
                     "DAC formatter/acceptance and receive mixer/FIR already included in loopback.",
                     "Converter reset alignment, carrier, fixtures and AM/PM differences unverified.",
                     "No frequency-to-phase integrator included; add it once if plant output is Hz."])
    for fixture in report["loopback"]:
        tau_s = fixture["delay_s"]+POST_IQ_DELAY_S
        h = electronics_response(np.array([0, fc_hz]), loopback_delay_s=fixture["delay_s"])
        assert np.isclose(h[0], GAIN_CODES_PER_RAD)
        assert np.allclose(abs(h), GAIN_CODES_PER_RAD)
        assert np.isclose(np.angle(h[1], deg=True), -360*fc_hz*tau_s)
        model["fixtures"].append(dict(source=fixture["file"],loopback_delay_s=fixture["delay_s"],
            total_delay_s=tau_s, phase_lag_at_crossover_deg=float(np.angle(h[1], deg=True))))
    (ROOT/"results/discriminator_model.json").write_text(json.dumps(model, indent=2)+"\n")
    latest_plot(latest, report["closed_loop"][0]["measured_response"])
    analyze_phase_noise()
    print(json.dumps(dict(latest_loop=report["closed_loop"][0], discriminator_model=model), indent=2))


if __name__ == "__main__":
    main()
