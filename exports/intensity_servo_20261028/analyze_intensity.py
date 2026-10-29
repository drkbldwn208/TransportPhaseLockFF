"""Fit intensity sensor maps, the AOM static slope, and the measured plant delay.

Run from any directory with Python + NumPy/SciPy/Pandas/Matplotlib. Raw CSVs are
read-only. The two attenuation-mode labels are inferred from power/count, not
encoded in the measurements. All controller results are model predictions.
"""
from pathlib import Path
import hashlib
import json
import os
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "intensity_20261028_matplotlib"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.integrate import cumulative_trapezoid
from scipy.stats import linregress

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
DATA = ROOT / "ILAData" / "10-28"
if not DATA.exists():
    DATA = OUT / "raw_data"  # Matched release package beside this script.
SENSOR_FILES = {
    "low_power": "tp_power_20261028T170653Z_8474d579.csv",
    "high_power": "tp_power_20261028T164507Z_a636b153.csv",
}


def save_json(name, contents):
    (OUT / name).write_text(json.dumps(contents, indent=2, allow_nan=False) + "\n")


def aom_log_slope(u_codes, alpha_rad_per_code):
    """RF envelope voltage is assumed proportional to nonnegative DAC code."""
    return 2 * alpha_rad_per_code / np.tan(alpha_rad_per_code * u_codes)


def fit_aom(u_codes, k_per_code):
    # Relative residuals prevent low-command, large slopes dominating the fit.
    # Robust loss reduces influence of the conspicuous 3k-code feature.
    result = least_squares(
        lambda scaled_alpha: (
            aom_log_slope(u_codes, scaled_alpha[0] * 1e-5) / k_per_code - 1
        ),
        [4.7], bounds=([0.01], [7.2]), loss="soft_l1", f_scale=0.03,
    )
    return float(result.x[0] * 1e-5)


def crossing_metrics(f_hz, response):
    """All crossings in the measured band; no stability inference beyond it."""
    logf = np.log(f_hz)
    mag_db = 20 * np.log10(abs(response))
    phase_deg = np.unwrap(np.angle(response)) * 180 / np.pi
    # Here the lowest measured frequency has phase between -180 and 0 degrees.
    gain_crossings = []
    for i in np.where(mag_db[:-1] * mag_db[1:] < 0)[0]:
        t = -mag_db[i] / (mag_db[i + 1] - mag_db[i])
        gain_crossings.append({
            "frequency_hz": float(np.exp(logf[i] + t * (logf[i + 1] - logf[i]))),
            "phase_margin_deg": float(180 + phase_deg[i] + t * (phase_deg[i + 1] - phase_deg[i])),
            "direction": "down" if mag_db[i + 1] < mag_db[i] else "up",
        })
    phase_crossings = []
    for level in np.arange(-180, phase_deg.min() - 360, -360):
        for i in np.where((phase_deg[:-1] - level) * (phase_deg[1:] - level) < 0)[0]:
            t = (level - phase_deg[i]) / (phase_deg[i + 1] - phase_deg[i])
            phase_crossings.append({
                "frequency_hz": float(np.exp(logf[i] + t * (logf[i + 1] - logf[i]))),
                "gain_margin_db": float(-mag_db[i] - t * (mag_db[i + 1] - mag_db[i])),
            })
    return {"gain_crossings": gain_crossings, "phase_crossings": phase_crossings}


def main():
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DATA.glob("*.csv"))}
    save_json("source_hashes.json", manifest)
    assert manifest["aom_signed_slopes.csv"] == manifest["aom_signed_slopes (1).csv"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    sensor_summary = {}
    for mode, filename in SENSOR_FILES.items():
        df = pd.read_csv(DATA / filename).sort_values("setpoint")
        adc = df.setpoint.to_numpy(dtype=float)  # Assumed adc_bias=0, settled PI.
        power_mW = df.mean_W.to_numpy() * 1000
        assert np.all(np.diff(adc) > 0) and np.all(np.diff(power_mW) > 0)
        sensor = {"adc_counts": adc.tolist(), "optical_power": power_mW.tolist(), "power_units": "mW",
                  "source_file": filename, "adc_bias_counts_assumed": 0,
                  "mode_assignment_confirmed": True,
                  "mode_assignment_basis": "user confirmed higher optical power is high mode, both ADC biases zero",
                  "dark_subtraction_mW": None}
        save_json(f"sensor_{mode}.json", sensor)
        sensor_summary[mode] = {"source_file": filename, "adc_range_counts": [float(adc[0]), float(adc[-1])],
                                "power_range_mW": [float(power_mW[0]), float(power_mW[-1])]}
        ax[0].plot(adc, power_mW, ".-", label=mode.replace("_", " "))
        ax[1].plot((adc[1:] + adc[:-1])/2, np.diff(power_mW)/np.diff(adc), label=mode.replace("_", " "))
    ax[0].set(xlabel="ADC setpoint [counts; bias assumed zero]", ylabel="Measured optical power [mW]")
    ax[1].set(xlabel="ADC setpoint [counts]", ylabel="Local conversion [mW/count]")
    for a in ax: a.grid(alpha=.3); a.legend()
    fig.savefig(OUT / "sensor_maps.png", dpi=180); plt.close(fig)

    slopes = pd.read_csv(DATA / "aom_signed_slopes.csv")
    u = slopes.u_codes.to_numpy(); k = slopes.k_per_code.to_numpy()
    alpha = fit_aom(u, k)
    fitted = aom_log_slope(u, alpha)
    empirical_log_F = cumulative_trapezoid(k, u, initial=0)
    model_log_F = 2*np.log(np.sin(alpha*u))
    log_shape_error = empirical_log_F-model_log_F
    log_shape_error -= np.interp(6000, u, log_shape_error)
    rng = np.random.default_rng(20261028)
    bootstrap = []
    for _ in range(400):
        idx = rng.integers(0, len(u), len(u))
        bootstrap.append(fit_aom(u[idx], k[idx]))
    aom = {"model": "F(u)=sin(alpha*u)**2; K=dln(F)/du=2*alpha*cot(alpha*u)",
           "alpha_rad_per_code": alpha, "offset_codes": 0,
           "alpha_bootstrap_95_percentile_rad_per_code": np.percentile(bootstrap, [2.5, 97.5]).tolist(),
           "bootstrap_limitation": "bin-resampling repeatability only; excludes calibration/model error",
           "measured_command_range_codes": [float(u.min()), float(u.max())],
           "predicted_first_maximum_codes": float(np.pi/(2*alpha)),
           "F_at_largest_measured_command": float(np.sin(alpha*u.max())**2),
           "fit_fractional_rms": float(np.sqrt(np.mean((fitted/k-1)**2))),
           "fit_fractional_rms_above_4000_codes": float(np.sqrt(np.mean((fitted[u>4000]/k[u>4000]-1)**2))),
           "fit_fractional_maximum_error": float(np.max(abs(fitted/k-1))),
           "integrated_shape_comparison_anchor_codes": 6000,
           "integrated_shape_fractional_error_range_all": [float(np.expm1(log_shape_error).min()), float(np.expm1(log_shape_error).max())],
           "integrated_shape_fractional_error_range_above_4000": [float(np.expm1(log_shape_error[u>4000]).min()), float(np.expm1(log_shape_error[u>4000]).max())],
           "normalization": "F is an ideal-model efficiency coordinate, NOT measured absolute diffraction efficiency",
           "identifiable_power": "P=A_eff*F(u); A_eff includes actual incident power, maximum efficiency and collection losses",
           "not_calibrated": "below minimum measured command, beyond maximum, dark optical offset, RF-amplifier saturation"}
    save_json("aom_model.json", aom)
    slopes["fitted_k_per_code"] = fitted
    slopes["fit_fractional_residual"] = fitted/k-1
    slopes["integrated_F_relative_to_largest_measured_u"] = np.exp(empirical_log_F-empirical_log_F[-1])
    slopes["integrated_shape_error_anchored_at_6000_codes"] = np.expm1(log_shape_error)
    slopes.to_csv(OUT / "aom_slope_fit.csv", index=False)
    ug = np.linspace(u.min(), u.max(), 2049)
    pd.DataFrame({"u_codes": ug, "sin2_coordinate": np.sin(alpha*ug)**2,
                  "transmission_relative_to_measured_max": (np.sin(alpha*ug)/np.sin(alpha*u.max()))**2}).to_csv(
                      OUT / "aom_fitted_response.csv", index=False)
    fig, ax = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    ax[0].errorbar(u, k, yerr=slopes.k_sem, fmt=".", label="Measured bins")
    ax[0].plot(ug, aom_log_slope(ug, alpha), label="sin² model"); ax[0].legend()
    ax[0].set(xlabel="DAC envelope command [codes]", ylabel="d ln(P)/du [1/code]")
    ax[1].plot(u, 100*(k/fitted-1), ".-")
    ax[1].set(xlabel="DAC envelope command [codes]", ylabel="Measured / model − 1 [%]")
    ax[2].plot(ug, (np.sin(alpha*ug)/np.sin(alpha*u.max()))**2)
    ax[2].plot(u, np.exp(empirical_log_F-empirical_log_F[-1]), ".", ms=3, label="Integrated measured slopes")
    ax[2].legend()
    ax[2].set(xlabel="DAC envelope command [codes]", ylabel="Transmission / value at largest measured u")
    for a in ax: a.grid(alpha=.3)
    fig.savefig(OUT / "aom_fit.png", dpi=180); plt.close(fig)

    fra = pd.read_csv(DATA / "intensity_loop_171424_945111.csv")
    f = fra.frequency_hz.to_numpy()
    K = (fra.K_re + 1j*fra.K_im).to_numpy()
    L = (fra.loop_re + 1j*fra.loop_im).to_numpy()
    assert fra.plant_reliable.all() and fra.loop_reliable.all()
    phase_deg = np.unwrap(np.angle(K))*180/np.pi
    delay_windows = []
    for lo, hi in [(1e3, 1e6), (1e4, 1e6), (5e4, 1e6), (1e5, 5e5), (1e5, 1e6)]:
        sel = (f >= lo) & (f <= hi)
        fit = linregress(f[sel], phase_deg[sel])
        delay_windows.append({"range_hz": [lo, hi], "effective_delay_s": float(-fit.slope/360),
                              "formal_delay_standard_error_s": float(fit.stderr/360),
                              "phase_offset_deg": float(fit.intercept),
                              "phase_residual_max_deg": float(max(abs(phase_deg[sel]-fit.intercept-fit.slope*f[sel])))})
    # Amplitude model is descriptive; a Gaussian transit response is consistent
    # with a finite laser-beam waist crossing a traveling acoustic wave.
    sel = f >= 1e4
    fit_amp = linregress(f[sel]**2, np.log(abs(K[sel])))
    k0 = float(np.exp(fit_amp.intercept))
    f_gaussian = float(np.sqrt(-1/fit_amp.slope))
    tau = delay_windows[2]["effective_delay_s"]
    predicted = k0*np.exp(-(f/f_gaussian)**2)*np.exp(-2j*np.pi*f*tau)
    results = {"sensor_maps": sensor_summary, "sensor_labels_confirmed": True,
               "excluded_sensor_file": "tp_power_20261028T145105Z_02e81cf4.csv: two nearly constant dark readings, not an invertible calibration",
               "plant_delay_windows": delay_windows, "effective_plant_delay_s": tau,
               "delay_definition": "phase slope of K=Q/(P0*U): command tap through DAC/RF/AOM/PD/mixer/ADC/receive filter back to recorded sensor; excludes controller transfer",
               "timing_limitations": "user confirms INT2 receive filter included; no separate pure propagation or electronics/optical delay identification",
               "plant_static_fractional_gain_per_code": k0,
               "gaussian_amplitude_1e_frequency_hz": f_gaussian,
               "measured_frequency_range_hz": [float(f.min()), float(f.max())],
               "all_points_flagged_reliable_in_csv": True,
               "fractional_optical_modulation_peak_max": float(max(abs(fra.Q_re+1j*fra.Q_im)/fra.p0)),
               "linearity_limitation": "500-code injection produced up to50.4% peak optical modulation. Reliable CSV flag tests scatter/drift/clipping, not small-signal linearity. Repeat at half amplitude before final tuning.",
               "existing_loop": crossing_metrics(f, L),
               "plant_phase_at_500k_deg": float(np.interp(np.log(5e5), np.log(f), phase_deg)),
               "plant_phase_at_550k_deg": float(np.interp(np.log(5.5e5), np.log(f), phase_deg)),
               "effective_optical_scale_at_FRA_mW": float(np.median(fra.p0/np.sin(alpha*fra.u0_codes)**2)),
               "recommended_initial_target_crossover_hz": 300000,
               "user_observation": "User reports achieving above300kHz bandwidth with PI;300kHz is the next tuning target, not contradicted by this delay fit.",
               "requested_above_500k_supported": False,
               "reason": "Measured plant already has ~196 degrees lag at500kHz. A single lead stage cannot be judged by local phase margin alone; its rising gain risks later unity crossings."}
    highf = np.geomspace(f.min(), f.max(), 5000)
    interp_K = np.exp(np.interp(np.log(highf), np.log(f), np.log(abs(K))) +
                      1j*np.interp(np.log(highf), np.log(f), np.unwrap(np.angle(K))))
    # Model the same quantized half-rate recurrence as the hardware helper.
    # Tune gain against the measured plant, not against the old raw-count PI.
    update_hz = 122.88e6
    zinv = np.exp(-2j*np.pi*highf/update_hz)
    controller_candidates, candidate_curves = {}, {}
    specs = [
        ("PI", 300e3, [50e3], None, None, "requested300kHz experiment"),
        ("PII", 150e3, [400e3, 1e3], None, None, "lower-bandwidth higher-order starting point"),
        ("PIII", 150e3, [400e3, 1e3, 100], None, None, "lower-bandwidth higher-order starting point"),
        ("PI_lead_300k", 300e3, [300e3], 20e3, 200e3, "optional experimental alternative"),
        ("PI_lag_300k", 300e3, [5e3], 400e3, 270e3, "comparison only: less low-frequency gain"),
        ("PI_150k_fallback", 150e3, [400e3], None, None, "wider-margin fallback"),
    ]
    for name, fc, corners, zero, pole, role in specs:
        increments = [round(2*np.pi*corner/update_hz*2**24) for corner in corners]
        cshape = np.prod([1+a/2**24*zinv/(1-zinv) for a in increments], axis=0)
        shelf_gain, shelf_alpha = 4096, 0
        if zero is not None:
            shelf_gain = round(pole/zero*4096)
            shelf_alpha = round(-np.expm1(-2*np.pi*pole/update_hz)*2**30)
            state = (shelf_alpha/2**30)*zinv/(1-(1-shelf_alpha/2**30)*zinv)
            cshape *= 1+(shelf_gain/4096-1)*(1-state)
        delay = (13 if zero is not None else 11)/245.76e6
        gain = float(1/np.interp(fc, highf, abs(interp_K/k0*cshape)))
        gain_code = round(gain*4096)
        candidate = interp_K/k0*cshape*(gain_code/4096)*np.exp(-2j*np.pi*highf*delay)
        S = 1/(1+candidate)
        candidate_curves[name] = candidate
        controller_candidates[name] = {
            "definition": "C(s)=g*product(1+2*pi*f_i/s); optional (1+s/zero)/(1+s/pole); margins use quantized discrete recurrence",
            "role": role, "target_crossover_hz": fc,
            "proportional_gain": gain, "actual_quantized_proportional_gain": gain_code/4096,
            "integrator_corner_hz": corners, "coefficient_reference_update_rate_hz": update_hz,
            "kp_Q12": gain_code, "integrator_Q24": increments,
            "lead_lag_enabled": zero is not None, "lead_zero_hz": zero, "lead_pole_hz": pole,
            "lead_gain_Q12": shelf_gain, "lead_alpha_Q30": shelf_alpha,
            "additional_fast_path_delay_s": delay,
            "plant_normalization": "measured K divided by fitted DC K0; assumes exact local input/output linearization",
            "margins_in_measured_band": crossing_metrics(highf, candidate),
            "maximum_sensitivity_in_measured_band": float(max(abs(S))),
            "maximum_sensitivity_frequency_hz": float(highf[np.argmax(abs(S))]),
            "gain_at_highest_measured_frequency": float(abs(candidate[-1])),
            "not_applied_to_hardware": True,
        }
    # Explicit rejected high-BW example: local phase margin alone is insufficient.
    lead_examples = {}
    for name, fc, fi, fz, fp in [
        ("rejected_550k", 550e3, 20e3, 80e3, 2e6),
    ]:
        shape = (1+fi/(1j*highf))*(1+1j*highf/fz)/(1+1j*highf/fp)
        gain = float(1/np.interp(fc, highf, abs(interp_K/k0*shape)))
        response = gain*interp_K/k0*shape*np.exp(-2j*np.pi*highf*13/245.76e6)
        lead_examples[name] = {"gain": gain, "integrator_corner_hz": fi,
                               "lead_zero_hz": fz, "lead_pole_hz": fp,
                               "margins_in_measured_band": crossing_metrics(highf, response),
                               "gain_at_highest_measured_frequency": float(abs(response[-1])),
                               "approved_default": False}
    results["lead_examples"] = lead_examples
    results["controller_candidates"] = controller_candidates
    save_json("analysis_summary.json", results)
    save_json("controller_starting_points.json", controller_candidates)
    fig, ax = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    ax[0, 0].semilogx(f, 20*np.log10(abs(K/k0)), ".-", label="Measured")
    ax[0, 0].semilogx(f, 20*np.log10(abs(predicted/k0)), "--", label="Gaussian magnitude fit")
    ax[0, 0].set(ylabel="Plant magnitude / DC [dB]"); ax[0, 0].legend()
    ax[1, 0].semilogx(f, phase_deg, ".-", label="Measured plant")
    ax[1, 0].semilogx(f, -360*f*tau, "--", label=f"Delay {tau*1e6:.3f} µs")
    ax[1, 0].axhline(-180, color="k", lw=.7); ax[1, 0].legend()
    ax[1, 0].set(xlabel="Frequency [Hz]", ylabel="Unwrapped plant phase [deg]")
    ax[0, 1].semilogx(f, 20*np.log10(abs(L)), ".-", label="Existing loop")
    ax[1, 1].semilogx(f, np.unwrap(np.angle(L))*180/np.pi, ".-", label="Existing loop")
    for name in ("PI", "PI_lead_300k", "PI_150k_fallback"):
        candidate = candidate_curves[name]
        ax[0, 1].semilogx(highf, 20*np.log10(abs(candidate)), label=f"Predicted {name}")
        ax[1, 1].semilogx(highf, np.unwrap(np.angle(candidate))*180/np.pi)
    ax[0, 1].axhline(0, color="k", lw=.7); ax[0, 1].legend()
    ax[0, 1].set(ylabel="Loop magnitude [dB]")
    ax[1, 1].axhline(-180, color="k", lw=.7)
    ax[1, 1].set(xlabel="Frequency [Hz]", ylabel="Unwrapped loop phase [deg]")
    for a in ax.flat: a.grid(alpha=.3, which="both")
    fig.savefig(OUT / "plant_and_loop.png", dpi=180); plt.close(fig)
    print(json.dumps({"alpha_rad_per_code": alpha, "effective_delay_ns": tau*1e9,
                      "existing_loop": results["existing_loop"],
                      "controller_starting_points": controller_candidates}, indent=2))


if __name__ == "__main__":
    main()
