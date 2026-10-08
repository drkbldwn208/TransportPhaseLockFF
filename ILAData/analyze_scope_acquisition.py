#!/usr/bin/env python3
"""Measure the oscillation in scope_3/4/5: CH1 controller, CH2 phase error.

These stage-3 traces appear saturated. Do not convert the clipped voltage into
optical phase, frequency noise, or linewidth. Fundamental phase differences are
descriptive waveform measurements, not open-loop phase margins or loop delays.
The damped-sinusoid edge fit characterizes ringing without locating its cause.
Run with: python ILAData/analyze_scope_acquisition.py
"""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares, minimize_scalar


def read_trace(path):
    data = np.genfromtxt(path, delimiter=',', skip_header=2)
    valid = np.flatnonzero(np.isfinite(data).all(axis=1))
    # The export has blank voltage entries at its boundaries, but no inner gaps.
    assert len(valid) > 100 and np.all(np.diff(valid) == 1)
    time_s, controller_V, error_V = data[valid].T
    time_s = time_s - time_s[0]
    dt_s = float(np.median(np.diff(time_s)))
    np.testing.assert_allclose(np.diff(time_s), dt_s, rtol=1e-6, atol=1e-15)
    return time_s, controller_V, error_V, dt_s


def fit_fundamental(time_s, controller_V, error_V, dt_s):
    # A windowed FFT supplies an initial bin; a sinusoid fit refines frequency.
    # Odd harmonics remain in the residual because these waveforms are square.
    spectrum = abs(np.fft.rfft((error_V-error_V.mean())*np.hanning(len(time_s))))
    frequency_hz = np.fft.rfftfreq(len(time_s), dt_s)
    peak = np.argmax(spectrum[1:])+1
    bin_hz = frequency_hz[1]

    def fit_at(frequency_hz):
        angle = 2*np.pi*frequency_hz*time_s
        basis = np.column_stack((np.ones(len(time_s)), np.cos(angle), np.sin(angle)))
        coefficients = np.linalg.lstsq(basis, np.column_stack((controller_V, error_V)), rcond=None)[0]
        residual = error_V-basis@coefficients[:, 1]
        return float(np.mean(residual**2)), coefficients

    optimum = minimize_scalar(lambda f: fit_at(f)[0], method='bounded',
                              bounds=(frequency_hz[peak]-bin_hz, frequency_hz[peak]+bin_hz))
    _, coefficients = fit_at(optimum.x)
    phasors = coefficients[1]-1j*coefficients[2]
    return dict(frequency_hz=float(optimum.x),
                controller_to_error_fundamental_ratio=float(abs(phasors[0]/phasors[1])),
                controller_relative_phase_deg=float(np.angle(phasors[0]/phasors[1], deg=True)))


def rising_edges(time_s, error_V):
    # Hysteresis prevents noise near zero from counting one edge several times.
    low_V, high_V = np.quantile(error_V, [0.25, 0.75])
    middle_V = (high_V+low_V)/2
    hysteresis_V = (high_V-low_V)/4
    armed = False
    last_crossing_s = None
    crossings_s = []
    for i in range(1, len(time_s)):
        if error_V[i] < middle_V-hysteresis_V:
            armed = True
            last_crossing_s = None
        if armed and error_V[i-1] < middle_V <= error_V[i]:
            fraction = (middle_V-error_V[i-1])/(error_V[i]-error_V[i-1])
            last_crossing_s = time_s[i-1]+fraction*(time_s[i]-time_s[i-1])
        if armed and error_V[i] > middle_V+hysteresis_V and last_crossing_s is not None:
            crossings_s.append(last_crossing_s)
            armed = False
    return np.asarray(crossings_s)


def edge_model(time_us, parameters):
    baseline_V, amplitude_V, decay_us, frequency_MHz, phase_rad = parameters
    return baseline_V+amplitude_V*np.exp(-time_us/decay_us)*np.cos(
        2*np.pi*frequency_MHz*time_us+phase_rad)


def analyze(path):
    time_s, controller_V, error_V, dt_s = read_trace(path)
    fundamental = fit_fundamental(time_s, controller_V, error_V, dt_s)
    crossings_s = rising_edges(time_s, error_V)
    periods_s = np.diff(crossings_s)
    # Independent period check catches missed crossings or a harmonic FFT peak.
    np.testing.assert_allclose(1/np.median(periods_s), fundamental['frequency_hz'], rtol=0.01)
    assert np.all((periods_s > 0.5/fundamental['frequency_hz']) &
                  (periods_s < 1.5/fundamental['frequency_hz']))
    selected_s = crossings_s[(crossings_s > 0.5e-6) & (crossings_s < time_s[-1]-1.5e-6)]
    edge_time_s = np.arange(-0.5e-6, 1.5e-6, dt_s)
    edge_error_V = np.mean([np.interp(t+edge_time_s, time_s, error_V) for t in selected_s], axis=0)
    # Start after the main transition: fit only the overshoot and settling tail.
    fit_mask = (edge_time_s > 0.07e-6) & (edge_time_s < 1.2e-6)
    edge_time_us = edge_time_s*1e6
    fit = least_squares(
        lambda p: edge_model(edge_time_us[fit_mask], p)-edge_error_V[fit_mask],
        [1.07, 0.6, 0.35, 2.5, 3.0],
        bounds=([0.5, 0, 0.03, 1, -10], [1.5, 3, 2, 10, 10]))
    assert fit.success
    channels = {}
    for name, voltage_V in [('controller', controller_V), ('error', error_V)]:
        # Midpoint of the two populations avoids a duty-cycle-biased median.
        center_V = float(np.mean(np.quantile(voltage_V, [0.25, 0.75])))
        low_V = float(np.median(voltage_V[voltage_V < center_V]))
        high_V = float(np.median(voltage_V[voltage_V >= center_V]))
        channels[name] = dict(low_plateau_V=low_V, high_plateau_V=high_V,
                              plateau_span_V=high_V-low_V,
                              minimum_V=float(voltage_V.min()), maximum_V=float(voltage_V.max()),
                              fraction_within_100mV_of_plateaus=float(np.mean(
                                  (abs(voltage_V-low_V) < 0.1) | (abs(voltage_V-high_V) < 0.1))))
    result = dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  samples=len(time_s), sample_interval_s=dt_s, duration_s=len(time_s)*dt_s,
                  **fundamental, median_period_s=float(np.median(periods_s)),
                  period_std_s=float(periods_s.std()), averaged_rising_edges=len(selected_s),
                  **channels,
                  edge_ring_frequency_hz=float(fit.x[3]*1e6),
                  edge_ring_decay_s=float(fit.x[2]*1e-6),
                  edge_fit_rms_V=float(np.sqrt(np.mean(fit.fun**2))))
    return result, (time_s, controller_V, error_V), (edge_time_us, edge_error_V, fit.x)


def main():
    folder = Path(__file__).resolve().parent
    fig, axes = plt.subplots(3, 2, figsize=(12, 9), layout='constrained')
    results = []
    for row, number in enumerate((3, 4, 5)):
        result, trace, edge = analyze(folder/f'scope_{number}.csv')
        results.append(result)
        time_s, controller_V, error_V = trace
        ax = axes[row, 0]
        window = time_s < 20e-6
        ax.plot(time_s[window]*1e6, controller_V[window], lw=0.8, label='CH1 controller')
        ax.plot(time_s[window]*1e6, error_V[window], lw=0.8, label='CH2 error')
        ax.set(title=f"Scope {number}: {result['frequency_hz']/1e3:.1f} kHz sustained oscillation",
               xlabel='Time from first valid sample (µs)', ylabel='Voltage (V)', ylim=(-2.9, 2.9))
        ax.legend(loc='lower right', fontsize=8)
        ax.grid(alpha=0.2)
        ax = axes[row, 1]
        edge_time_us, edge_error_V, parameters = edge
        ax.plot(edge_time_us, edge_error_V, color='tab:orange', label='CH2 averaged rising edge')
        fit_time_us = np.linspace(0.07, 1.2, 400)
        ax.plot(fit_time_us, edge_model(fit_time_us, parameters), 'k--', lw=1,
                label=f"Damped fit: {parameters[3]:.2f} MHz, τ = {parameters[2]:.2f} µs")
        ax.set(title=f"Scope {number}: {result['averaged_rising_edges']} aligned transitions",
               xlabel='Time relative to CH2 mid-level crossing (µs)', ylabel='Error voltage (V)')
        ax.legend(loc='lower right', fontsize=8)
        ax.grid(alpha=0.2)
    fig.suptitle('Stage 3 with EOM feedback: repeated saturation and faster edge ringing', fontsize=14)
    fig.savefig(folder/'scope_acquisition_analysis.png', dpi=180)
    plt.close(fig)
    output = dict(
        interpretation='Voltage-domain measurements only; no optical phase reconstruction from saturated data.',
        user_report='Stage 3; EOM gain decreased across captures; CH1 controller output, CH2 error.',
        cautions=['CH1 plateaus do not alone prove that the controller itself is clipping.',
                  'A fitted fundamental phase is not a loop phase-margin or propagation-delay measurement.',
                  'Edge-ring fit is descriptive and does not identify the ringing component.',
                  'CSV scope voltages used as exported; no subtraction of screen position.'],
        traces=results)
    (folder/'scope_acquisition_analysis.json').write_text(json.dumps(output, indent=2)+'\n')
    for r in results:
        print(f"{r['file']}: {r['frequency_hz']/1e3:.2f} kHz, "
              f"CH1 plateau span {r['controller']['plateau_span_V']:.3f} V, "
              f"CH2 plateau span {r['error']['plateau_span_V']:.3f} V, "
              f"edge ring {r['edge_ring_frequency_hz']/1e6:.3f} MHz")


if __name__ == '__main__':
    main()
