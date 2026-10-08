#!/usr/bin/env python3
"""Estimate beat linewidth from a calibrated, phase-only scope voltage.

Assumes gain 1, approximately 2 V per 2*pi, sample acquisition (not waveform
averaging), and negligible measurement filtering over the line. The user reports
slow piezo feedback, EOM off, and a narrow optical reference. Thus this measures
the spectrum under piezo feedback, not a fully open-loop or intrinsic linewidth.
Capture/derivative output must be OFF; this remains a condition on the estimate.

Use exp(i*phase) rather than FFT(voltage) or unwrapping sparse samples. Estimate
g1(tau)=mean[z(t+tau)*conj(z(t))], fit its initial decay to a Voigt correlation,
and independently plot the complex-field Welch spectrum. No FPGA files change.
Method reference: Di Domenico et al., Applied Optics 49, 4801 (2010),
https://doi.org/10.1364/AO.49.004801, equations 1 and 2.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import brentq, lsq_linear
from scipy.signal import welch
from scipy.special import voigt_profile
from analyze_laser_pll_adc import plt


def read_trace(path):
    with path.open() as stream:
        rows = list(csv.reader(stream))
    metadata = {row[0]: row[1] for row in rows if row[0]}
    time_s = np.array([float(row[3]) for row in rows])
    voltage_V = np.array([float(row[4]) for row in rows])
    dt_s = float(np.median(np.diff(time_s)))
    np.testing.assert_allclose(np.diff(time_s), dt_s, rtol=1e-6)
    if metadata['Source'] != 'CH2':
        raise ValueError('Expected channel 2.')
    return time_s, voltage_V, dt_s, metadata


def coherence(field, lags):
    return np.array([np.mean(field[k:]*field[:-k].conj()) for k in lags])


def fit_coherence(correlation, tau_s):
    # g1 magnitude = C exp(-a*tau_us - b*tau_us^2). C absorbs unresolved fast
    # decorrelation; a/b describe a Lorentzian/Gaussian mixture, not identified
    # microscopic noise sources. Avoid fitting long lags at the sample-noise floor.
    tau_us = tau_s*1e6
    design = np.column_stack((np.ones(len(tau_s)), tau_us, tau_us**2))
    log_amplitude, a, b = lsq_linear(
        design, -np.log(np.clip(abs(correlation), 1e-6, 1)), bounds=(0, np.inf)).x
    lorentz_hwhm_hz = a*1e6/(2*np.pi)
    gaussian_sigma_hz = np.sqrt(b)*1e6/(np.sqrt(2)*np.pi)
    width_scale_hz = lorentz_hwhm_hz+gaussian_sigma_hz
    peak = voigt_profile(0, gaussian_sigma_hz, lorentz_hwhm_hz)
    half_width_hz = brentq(lambda f: voigt_profile(
        f, gaussian_sigma_hz, lorentz_hwhm_hz)-peak/2, 0, 20*width_scale_hz)
    return dict(fwhm_hz=2*half_width_hz, correlation_amplitude=float(np.exp(-log_amplitude)),
                lorentz_fwhm_hz=float(2*lorentz_hwhm_hz),
                gaussian_fwhm_hz=float(np.sqrt(8*np.log(2))*gaussian_sigma_hz),
                a_per_us=float(a), b_per_us2=float(b))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase-span-v', type=float, default=2.0)
    args = parser.parse_args()
    if args.phase_span_v <= 0:
        parser.error('The voltage span for 2*pi must be positive.')
    folder = Path(__file__).resolve().parent
    paths = [folder/'TEK0003.CSV', folder/'TEK0004.CSV']
    traces = [read_trace(path) for path in paths]
    time_s, voltage_V, dt_s, _ = traces[1]
    field = np.exp(2j*np.pi*voltage_V/args.phase_span_v)
    fit_lags = np.arange(1, 7)  # 0.4..2.4 us, before coherence disappears
    fit = fit_coherence(coherence(field, fit_lags), fit_lags*dt_s)
    # Block resampling preserves local dynamics and avoids artificial phase
    # joins. This scatter excludes calibration, detector and line-shape errors.
    blocks = np.array_split(field, 20)  # 50 us each
    block_correlations = np.array([coherence(block, fit_lags) for block in blocks])
    rng = np.random.default_rng(7)
    widths_hz = []
    for _ in range(500):
        draw = block_correlations[rng.integers(0, len(blocks), len(blocks))].mean(axis=0)
        widths_hz.append(fit_coherence(draw, fit_lags*dt_s)['fwhm_hz'])
    calibration = {}
    for scale in (0.9, 1.0, 1.1):
        span = args.phase_span_v*scale
        z = np.exp(2j*np.pi*voltage_V/span)
        calibration[str(span)] = fit_coherence(coherence(z, fit_lags), fit_lags*dt_s)['fwhm_hz']
    segment_widths = [fit_coherence(coherence(part, fit_lags), fit_lags*dt_s)['fwhm_hz']
                      for part in np.array_split(field, 5)]
    result = dict(
        method='Conditional reconstruction of phase-only voltage as exp(i*2*pi*V/phase_span_V)',
        phase_span_V=args.phase_span_v, capture_derivative_off_required=True,
        feedback='Slow piezo on; EOM off; narrow optical reference (user reports)',
        files=[dict(name=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    samples=len(trace[0]), sample_interval_s=trace[2],
                    duration_s=len(trace[0])*trace[2], metadata=trace[3])
               for path, trace in zip(paths, traces)],
        tek4_voigt_coherence_fit=fit,
        bootstrap_width_percentiles_2p5_50_97p5_hz=np.quantile(widths_hz, [.025, .5, .975]).tolist(),
        calibration_sensitivity_span_V_to_width_Hz=calibration,
        widths_of_five_200us_segments_hz=segment_widths,
        limitations=[
            'Valid only for phase-only output, not phase-plus-frequency or railed unwrapped error.',
            '2 V per 2*pi is approximate; scope acquisition mode and analog transfer are unverified.',
            'The line is not purely Lorentzian; fitted Lorentzian term is not an intrinsic linewidth measurement.',
            'Slow piezo feedback remains active; the 1-ms line can include servo effects and drift.',
            'TEK3 Nyquist span is only +/-125 kHz, insufficient for the inferred broad line.',
            'Finite-record scatter does not include instrument systematic error.'])
    out = folder/'scope_linewidth_analysis'
    out.with_suffix('.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for ax, trace, path in zip(axes[0], traces, paths):
        t, voltage, interval, _ = trace
        ax.plot((t-t[0])*1e3, voltage, lw=0.65)
        ax.set(xlabel='Time within record (ms)', ylabel='CH2 voltage (V)',
               title=f'{path.stem}: {interval*1e6:g} µs/sample')
    lags = np.arange(1, 26)
    c = coherence(field, lags)
    tau_us = lags*dt_s*1e6
    axes[1, 0].plot(tau_us, abs(c), 'o', ms=4, label='TEK4 measured coherence')
    fine_tau_us = np.linspace(0, tau_us[-1], 400)
    fitted = fit['correlation_amplitude']*np.exp(
        -fit['a_per_us']*fine_tau_us-fit['b_per_us2']*fine_tau_us**2)
    axes[1, 0].plot(fine_tau_us, fitted, label=f'Voigt decay fit: {fit["fwhm_hz"]/1e3:.0f} kHz FWHM')
    axes[1, 0].axvspan(.4, 2.4, color='gray', alpha=.1, label='Fit interval')
    axes[1, 0].set(xlabel='Phase-sample separation τ (µs)', ylabel='|g₁(τ)|', ylim=(0, 1.05))
    axes[1, 0].legend(fontsize=8)
    f, psd = welch(field, fs=1/dt_s, nperseg=128, noverlap=64,
                   detrend=False, return_onesided=False)
    order = np.argsort(f)
    axes[1, 1].plot(f[order]/1e3, psd[order]*1e6, lw=1)
    axes[1, 1].set(xlabel='Frequency relative to DDS (kHz; sign may reverse)',
                   ylabel='Reconstructed field PSD (1/MHz)', xlim=(-800, 800),
                   title='TEK4 complex-field spectrum; broad, non-Lorentzian line')
    for ax in axes.flat:
        ax.grid(alpha=.25)
    fig.suptitle(f'Conditional linewidth estimate: phase-only CH2, {args.phase_span_v:g} V per 2π\n'
                 'Slow piezo on; narrow reference; 1-ms linewidth is not the intrinsic linewidth', fontsize=11)
    fig.savefig(out.with_suffix('.png'), dpi=170)
    plt.close(fig)


if __name__ == '__main__':
    main()
