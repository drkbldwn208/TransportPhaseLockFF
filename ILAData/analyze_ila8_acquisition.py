#!/usr/bin/env python3
"""Diagnose phase continuity and the old entry gate from the ILA 8 RTL replay.

Run plot_laser_pll_error.py with --adc-slot 9 first. This script changes no RTL
or project files. The reconstructed reference, gains and phase origin are the
assumptions recorded in iladata8_phase_error.json, not captured GPIO settings.
The incorrectly exported scope file is excluded from this analysis.
"""
import json
from pathlib import Path

import numpy as np
from analyze_laser_pll_adc import plt


def longest_run(mask):
    edges = np.diff(np.r_[False, mask, False].astype(int))
    lengths = np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)
    return int(max(lengths, default=0))


def main():
    folder = Path(__file__).resolve().parent
    replay_path = folder / 'iladata8_phase_error.csv'
    data = np.genfromtxt(replay_path, names=True, delimiter=',')
    assumptions = json.loads(replay_path.with_suffix('.json').read_text())
    rate_hz = assumptions['sample_rate_hz'] / 8
    dt_s = 1 / rate_hz
    time_s = data['adc_word_time_s']
    valid = data['phase_valid'].astype(bool)
    if not np.all(valid):
        raise ValueError('Do not unwrap across invalid phase samples.')
    phase_rad = np.unwrap(data['phase_error_rad'])
    frequency_hz = data['frequency_error_hz']  # reference minus beat
    amplitude_counts = np.hypot(data['i_adc_counts'], data['q_adc_counts'])
    phase_slope, phase_intercept = np.polyfit(time_s-time_s.mean(), phase_rad, 1)
    phase_residual_rad = phase_rad - (phase_slope*(time_s-time_s.mean())+phase_intercept)
    delta_rad = np.angle(np.exp(1j*np.diff(data['phase_error_rad'])))
    np.testing.assert_allclose(delta_rad/(2*np.pi*dt_s), frequency_hz[1:], atol=1e-5)
    # A 25-clock phase difference is diagnostic averaging only, not a new filter
    # in the FPGA. It makes the derivative's dependence on observation time clear.
    average_clocks = 25
    average_time_s = (time_s[average_clocks:]+time_s[:-average_clocks])/2
    average_frequency_hz = (phase_rad[average_clocks:]-phase_rad[:-average_clocks]) / (
        2*np.pi*average_clocks*dt_s)
    in_old_band = abs(frequency_hz) <= 3e6
    result = dict(
        capture_sha256=assumptions['sha256'], reference_hz=assumptions['reference_hz'],
        assumed_control=assumptions['assumed_control'],
        analyzed_samples=len(time_s), analyzed_duration_us=len(time_s)*dt_s*1e6,
        phase_valid_fraction=float(valid.mean()),
        amplitude_counts_min_median_max=[float(amplitude_counts.min()),
                                         float(np.median(amplitude_counts)), float(amplitude_counts.max())],
        phase_rms_about_mean_rad=float(phase_rad.std()), phase_peak_to_peak_rad=float(np.ptp(phase_rad)),
        phase_linear_fit_residual_rms_rad=float(phase_residual_rad.std()),
        largest_adjacent_phase_step_rad=float(abs(delta_rad).max()),
        fitted_ref_minus_beat_hz=float(phase_slope/(2*np.pi)),
        instantaneous_ref_minus_beat_hz=dict(min=float(frequency_hz.min()),
            max=float(frequency_hz.max()), rms_about_mean=float(frequency_hz.std())),
        average_frequency_interval_ns=average_clocks*dt_s*1e9,
        average_ref_minus_beat_hz=dict(min=float(average_frequency_hz.min()),
            max=float(average_frequency_hz.max()), rms_about_mean=float(average_frequency_hz.std())),
        old_gate=dict(outside_3MHz_samples=int((~in_old_band).sum()),
            outside_fraction=float((~in_old_band).mean()),
            longest_in_band_clocks=longest_run(in_old_band),
            longest_in_band_us=longest_run(in_old_band)*dt_s*1e6,
            required_in_band_clocks=4096, required_in_band_us=4096*dt_s*1e6),
        rtl_vs_float_max_phase_error_rad=assumptions['rtl_vs_float_max_phase_error_rad'],
        voltage_predictions_assuming_2Vpp_gain1=dict(
            phase_only_rms_about_mean_V=float(phase_rad.std()/np.pi),
            phase_only_peak_to_peak_V=float(np.ptp(phase_rad)/np.pi),
            capture64_rail_fraction=assumptions['capture_on']['rail_fraction']),
        limitations=[
            'Reference/gain/phase origin are replay assumptions, not live settings.',
            'ILA 8 captures raw ADC, not this PLL\'s actual extracted phase or DAC bus.',
            'ILA acquisition/FFT status probes 14/15 are only one bit wide.',
            'Incorrect scope export excluded at user request.',
            'Short records cannot establish millisecond optical capture or controller stability.'])
    out = folder / 'iladata8_acquisition_analysis'
    out.with_suffix('.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True, constrained_layout=True)
    axes[0].plot(time_s*1e6, amplitude_counts/1000, lw=0.8)
    axes[0].set(ylabel='I/Q magnitude\n(1000 ADC counts)',
                title='No amplitude collapse: minimum 4242 counts; assumed validity threshold 64')
    axes[1].plot(time_s*1e6, phase_rad-phase_rad.mean(), lw=0.8)
    axes[1].set(ylabel='Phase error (rad)\nmean removed',
                title=f'Phase excursion {np.ptp(phase_rad):.3f} rad peak-to-peak; '
                      f'largest adjacent step {abs(delta_rad).max():.3f} rad')
    axes[2].plot(time_s*1e6, frequency_hz/1e6, lw=0.6, alpha=0.65,
                 label='4.07 ns phase difference (hardware frequency diagnostic)')
    axes[2].plot(average_time_s*1e6, average_frequency_hz/1e6, lw=1,
                 color='black', label='101.7 ns phase difference (analysis only)')
    for limit in (-3, 3):
        axes[2].axhline(limit, color='tab:red', ls='--', lw=1)
    axes[2].set(ylabel='Reference − beat (MHz)', xlabel='Captured ADC word time (µs)',
                title='Old ±3 MHz gate: longest passing stretch 0.537 µs; required 16.667 µs')
    axes[2].legend(fontsize=8, loc='lower right')
    for ax in axes:
        ax.grid(alpha=0.25)
    fig.suptitle('ILA 8: raw ADC replay through RTL, assuming an 800 MHz reference\n'
                 'Phase extraction is continuous; the old consecutive-sample gate repeatedly resets', fontsize=11)
    fig.savefig(out.with_suffix('.png'), dpi=170)
    plt.close(fig)



if __name__ == '__main__':
    main()
