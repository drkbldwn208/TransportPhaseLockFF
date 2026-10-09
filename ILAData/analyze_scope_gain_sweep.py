#!/usr/bin/env python3
"""Analyze scope_6..11: slow feedback on, undivided stage-3 phase detector.

CH1 is FALC output; CH2 is the FPGA error after analog conversion. These are
voltage-domain diagnostics of saturated acquisition, not optical linewidth or
small-signal phase-margin measurements. CSV timestamps and voltages are used
directly; scope screen positions are not subtracted. Some TXT display timebases
cover only part of the longer exported CSV records.
"""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analyze_scope_acquisition import read_trace, rising_edges


SETTINGS = {
    6: "Fast output disabled/reset",
    7: "Fast output disabled/reset",
    8: "Fast gain below rapid oscillation",
    9: "Fast gain just above onset",
    10: "High fast gain, original offset",
    11: "High fast gain, changed offset",
}


def analyze(path):
    time_s, controller_V, error_V, dt_s = read_trace(path)
    middle_V = np.mean(np.quantile(error_V, [0.25, 0.75]))
    low_V = float(np.median(error_V[error_V < middle_V]))
    high_V = float(np.median(error_V[error_V >= middle_V]))
    middle_V = (low_V + high_V) / 2
    rising_s = rising_edges(time_s, error_V)
    falling_s = rising_edges(time_s, -error_V)
    period_s = np.diff(rising_s)
    assert len(period_s) >= 2
    median_period_s = float(np.median(period_s))
    # This estimates proximity to observed plateaus, not the FPGA saturation bit.
    plateau_mask = (abs(error_V-low_V) < 0.1) | (abs(error_V-high_V) < 0.1)
    central_mask = abs(error_V-middle_V) < (high_V-low_V)/4
    result = dict(
        file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        samples=len(time_s), sample_interval_s=dt_s, duration_s=len(time_s)*dt_s,
        error_low_plateau_V=low_V, error_high_plateau_V=high_V,
        fraction_error_within_100mV_of_plateaus=float(np.mean(plateau_mask)),
        fraction_error_in_central_half_span=float(np.mean(central_mask)),
        fraction_error_above_midpoint=float(np.mean(error_V > middle_V)),
        controller_mean_V=float(np.mean(controller_V)),
        controller_1st_99th_percentile_V=np.quantile(controller_V, [.01,.99]).tolist(),
        fraction_controller_outside_4V=float(np.mean(abs(controller_V) > 4)),
        error_rising_edges=len(rising_s), median_rising_period_s=median_period_s,
        inverse_median_rising_period_hz=1/median_period_s,
        rising_period_10th_90th_percentile_s=np.quantile(period_s, [.1,.9]).tolist(),
        rising_periods_over_twice_median_s=period_s[period_s > 2*median_period_s].tolist(),
    )
    # For a railed CH1, measure recovery after a positive CH2 transition. The
    # 0.4 V release threshold exceeds the ~0.08 V digitization/noise scale.
    negative_rail_V = float(np.quantile(controller_V, .1))
    recovery = []
    if negative_rail_V < -4:
        for edge_s in rising_s:
            next_fall = falling_s[falling_s > edge_s]
            if not len(next_fall):
                continue
            indices = np.flatnonzero((time_s >= edge_s) & (time_s < next_fall[0]))
            if not len(indices) or controller_V[indices[0]] > negative_rail_V+0.4:
                continue
            leaving = indices[controller_V[indices] > negative_rail_V+0.4]
            crossing = indices[controller_V[indices] > 0]
            if len(leaving) and len(crossing):
                recovery.append(dict(error_rising_time_s=float(edge_s),
                                     release_delay_s=float(time_s[leaving[0]]-edge_s),
                                     zero_crossing_delay_s=float(time_s[crossing[0]]-edge_s)))
    result['controller_recovery_after_error_rise'] = recovery
    return result, (time_s, controller_V, error_V)


def draw_trace(ax, trace, window_s, time_scale, unit, title):
    time_s, controller_V, error_V = trace
    visible = (time_s >= window_s[0]) & (time_s <= window_s[1])
    ax.plot(time_s[visible]*time_scale, controller_V[visible], lw=.75,
            label="CH1: FALC output", color="tab:blue")
    ax.plot(time_s[visible]*time_scale, error_V[visible], lw=.75,
            label="CH2: error", color="tab:orange")
    ax.set(title=title, xlabel=f"Time from record start ({unit})", ylabel="Voltage (V)")
    ax.grid(alpha=.2)
    ax.legend(loc="upper right", fontsize=8)


def main():
    folder = Path(__file__).resolve().parent
    results, traces = {}, {}
    for number in SETTINGS:
        results[number], traces[number] = analyze(folder/f"scope_{number}.csv")
        results[number]['setting'] = SETTINGS[number]

    fig, axes = plt.subplots(3, 2, figsize=(13, 10), layout="constrained")
    windows = {6: (0,.012), 7: (0,.01), 8: (0,.01),
               9: (0,50e-6), 10: (0,500e-6), 11: (0,.002)}
    for ax, number in zip(axes.flat, SETTINGS):
        result = results[number]
        scale, unit = (1e6, "µs") if number in (9,10) else (1e3, "ms")
        rate_hz = result['inverse_median_rising_period_hz']
        rate = f"{rate_hz:.0f} Hz" if rate_hz < 1000 else f"{rate_hz/1000:.1f} kHz"
        draw_trace(ax, traces[number], windows[number], scale, unit,
                   f"Scope {number}: {SETTINGS[number]}\nError switching ≈{rate}")
    fig.suptitle("Undivided stage 3: slow rail switching, rapid limit cycle, and saturation recovery",
                 fontsize=13)
    fig.savefig(folder/'scope_gain_sweep.png', dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(13, 7), layout="constrained")
    details = [(9, (0,20e-6)), (10, (0,100e-6)),
               (11, (0,400e-6)), (8, (0,1.2e-3))]
    for ax, (number, window) in zip(axes.flat, details):
        draw_trace(ax, traces[number], window, 1e6, "µs",
                   f"Scope {number}: {SETTINGS[number]}")
        if number == 11:
            first = results[11]['controller_recovery_after_error_rise'][0]
            start_us = first['error_rising_time_s']*1e6
            end_us = start_us + first['release_delay_s']*1e6
            ax.axvspan(start_us, end_us, color='gray', alpha=.15)
            ax.text((start_us+end_us)/2, -2.2,
                    f"CH1 remains near negative rail\nfor {end_us-start_us:.0f} µs after CH2 rises",
                    ha='center', fontsize=8)
    fig.suptitle("Voltage details: CH2 remains at a plateau even during slow CH1 recovery", fontsize=13)
    fig.savefig(folder/'scope_gain_sweep_details.png', dpi=180)
    plt.close(fig)

    output = dict(
        hardware="Old undivided stage 3; these captures do not test the new A4 /160 mapping.",
        feedback="Piezo on throughout. Fast output disabled/reset in 6/7; filter switches unchanged.",
        cautions=["Switching rate of clipped error is not optical frequency detuning.",
                  "Plateau proximity is a voltage estimate, not a recorded saturation flag.",
                  "CH1 plateaus alone do not locate the internal controller limiter.",
                  "Use CSV record times; TXT display timebases/statistics need not describe the full record.",
                  "No linewidth, phase-margin, or EOM tuning coefficient is inferred from clipped traces."],
        traces=list(results.values()))
    (folder/'scope_gain_sweep.json').write_text(json.dumps(output, indent=2)+'\n')
    for number, result in results.items():
        print(f"Scope {number}: {result['inverse_median_rising_period_hz']:.1f} Hz, "
              f"error near plateaus {100*result['fraction_error_within_100mV_of_plateaus']:.2f}%, "
              f"CH1 |V|>4 V {100*result['fraction_controller_outside_4V']:.2f}%")
    print("Scope 11 recovery:", results[11]['controller_recovery_after_error_rise'])


if __name__ == '__main__':
    main()
