#!/usr/bin/env python3
"""Separate a clean tone's phase fluctuations from its deterministic phase ramp.

First run plot_laser_pll_error.py, then for example:
  python3 ILAData/measure_laser_pll_phase_noise.py ILAData/iladata7_phase_error.csv

Fits a straight line to unwrapped RTL phase, removing constant frequency offset
and arbitrary NCO phase. This is appropriate for a coherent, nearly steady tone
with uninterrupted valid phase samples, not for arbitrary laser acquisition.
Capture noise is e_residual + G * delta_phase_residual, using the RTL frequency
discriminator. Noise voltages are before clipping and RFDC/analog/scope filtering.
Peak-to-peak values describe only this short record, not long-term extremes.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from analyze_laser_pll_adc import plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('replay_csv', type=Path)
    parser.add_argument('--full-scale-vpp', type=float, default=2.0)
    args = parser.parse_args()
    if args.full_scale_vpp <= 0:
        parser.error('Full-scale voltage span must be positive.')
    data = np.genfromtxt(args.replay_csv, names=True, delimiter=',')
    metadata = json.loads(args.replay_csv.with_suffix('.json').read_text())
    if not np.all(data['phase_valid']):
        parser.error('Phase contains invalid samples; use the I/Q diagnostic plot instead.')
    control = int(metadata['assumed_control'], 0)
    gain = 1 << ((control >> 4) & 15)
    polarity = -1 if control & 4 else 1
    error_rate_hz = metadata['sample_rate_hz']/8
    time_s = data['adc_word_time_s']
    centered_time_s = time_s-time_s.mean()
    phase_rad = np.unwrap(data['phase_error_rad'])
    phase_slope_rad_s, phase_intercept_rad = np.polyfit(centered_time_s, phase_rad, 1)
    ramp_rad = phase_slope_rad_s*centered_time_s+phase_intercept_rad
    residual_rad = phase_rad-ramp_rad
    delta_rad = data['frequency_error_hz']*2*np.pi/error_rate_hz
    delta_residual_rad = delta_rad-phase_slope_rad_s/error_rate_hz
    mv_per_rad = polarity*gain*args.full_scale_vpp*1000/(2*np.pi)
    weights = (0, 1, 2, 4, 8, 16, 32, 64)
    noise_mv = {weight: (residual_rad+weight*delta_residual_rad)*mv_per_rad
                for weight in weights}
    statistics = {}
    for weight, values in noise_mv.items():
        statistics[str(weight)] = dict(
            rms_mv=float(np.std(values)), peak_to_peak_mv=float(np.ptp(values)),
            frequency_term_dc_mv=float(weight*phase_slope_rad_s/error_rate_hz*mv_per_rad))
    result = dict(
        source_replay=str(args.replay_csv), capture_sha256=metadata['sha256'],
        full_scale_vpp=args.full_scale_vpp, phase_gain=gain,
        fitted_input_minus_reference_hz=float(-phase_slope_rad_s/(2*np.pi)),
        analyzed_duration_us=float(len(time_s)/error_rate_hz*1e6),
        phase_residual_rms_rad=float(np.std(residual_rad)),
        phase_residual_peak_to_peak_rad=float(np.ptp(residual_rad)),
        capture_weight_noise_before_clipping=statistics,
        ideal_saw_step_mv=float(abs(phase_slope_rad_s/error_rate_hz*mv_per_rad)),
        notes='Constant phase and linear drift removed. No extra digital filtering. '
              'Capture weight zero means capture disabled. RMS/peak-to-peak are noise '
              'about the ramp, not the RMS of the whole sawtooth. Capture predictions '
              'exclude clipping and RFDC/analog/scope response. Voltage calibration and '
              'gain settings are assumptions; this ILA does not record live controls.')
    output = args.replay_csv.with_name(args.replay_csv.stem.replace('_phase_error', '_phase_noise'))
    output.with_suffix('.json').write_text(json.dumps(result, indent=2)+'\n')
    np.savetxt(output.with_suffix('.csv'),
               np.column_stack([time_s, residual_rad, *noise_mv.values()]), delimiter=',', comments='',
               header='adc_word_time_s,phase_residual_rad,'+
                      ','.join(f'noise_capture_weight_{weight}_mv' for weight in weights))
    print(json.dumps(result, indent=2))

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, constrained_layout=True)
    axes[0].plot(time_s*1e6, data['dac_phase_only_counts']*args.full_scale_vpp/65536, lw=0.8)
    axes[0].set(ylabel='Predicted output (V)', title='Capture OFF: actual RTL DAC codes, scaled to volts')
    axes[1].plot(time_s*1e6, noise_mv[0], lw=0.65)
    axes[1].set(ylabel='Residual (mV)',
                title=f'Capture OFF: phase ramp removed — {statistics["0"]["rms_mv"]:.3f} mV RMS, '
                      f'{statistics["0"]["peak_to_peak_mv"]:.2f} mV peak-to-peak')
    for weight in (64, 16):
        axes[2].plot(time_s*1e6, noise_mv[weight], lw=0.65, alpha=0.85,
                     label=f'Weight {weight}: {statistics[str(weight)]["rms_mv"]:.2f} mV RMS')
    axes[2].set(ylabel='Residual (mV)', xlabel='Captured ADC word time (µs)',
                title='Capture ON: noise about the ramp, before clipping')
    axes[2].legend(loc='upper right')
    for ax in axes:
        ax.grid(alpha=0.25)
    fig.suptitle(f'{output.stem}: {metadata["reference_hz"]/1e6:g} MHz reference, gain {gain}, '
                 f'{args.full_scale_vpp:g} Vpp full scale\n'
                 'Absolute NCO phase assumed; no RFDC/analog/scope filtering', fontsize=12)
    fig.savefig(output.with_suffix('.png'), dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    main()
