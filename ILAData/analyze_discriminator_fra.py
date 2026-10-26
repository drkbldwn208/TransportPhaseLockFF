"""Inspect measured return ratio and a conditional half-gain prediction.

Use E/U phasors, exclude flagged points when locating crossover, and choose the
phase branch near -180 degrees locally. Do not unwrap through low-SNR points.
The prediction assumes the same linear plant/controllers and operating point.
"""
from pathlib import Path
import hashlib
import json
import os

os.environ.setdefault('MPLCONFIGDIR', '/tmp/discriminator_fra_mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'10-13FRA/Discriminator/laser_loop_20261014_050122.csv'
OUTPUT = SOURCE.with_name(SOURCE.stem+'_interpreted')


def crossover(frequency_hz, loop):
    gain_db = 20*np.log10(abs(loop))
    phase_deg = np.unwrap(np.angle(loop))*180/np.pi
    phase_deg -= 360*round((np.median(phase_deg)+150)/360)
    pairs = np.flatnonzero((gain_db[:-1] >= 0) & (gain_db[1:] < 0))
    assert len(pairs) == 1, 'Expected one main downward unity-gain crossing in this band.'
    k = pairs[0]
    weight = -gain_db[k]/(gain_db[k+1]-gain_db[k])
    fc_hz = np.exp(np.log(frequency_hz[k])+weight*np.log(frequency_hz[k+1]/frequency_hz[k]))
    phase = phase_deg[k]+weight*(phase_deg[k+1]-phase_deg[k])
    sensitivity_db = 20*np.log10(abs(1/(1+loop)))
    peak = np.argmax(sensitivity_db)
    return dict(crossover_hz=float(fc_hz), phase_at_crossover_deg=float(phase),
                local_phase_margin_deg=float(180+phase),
                peak_sensitivity_db=float(sensitivity_db[peak]),
                peak_sensitivity_frequency_hz=float(frequency_hz[peak]))


def main():
    d = pd.read_csv(SOURCE)
    f = d.frequency_hz.to_numpy()
    error = d.error_re.to_numpy()+1j*d.error_im.to_numpy()
    drive = d.drive_re.to_numpy()+1j*d.drive_im.to_numpy()
    loop = -error/drive
    sensitivity = drive/(drive-error)
    reliable = d.reliable.to_numpy(dtype=bool)
    assert np.all(np.diff(f) > 0)
    assert np.allclose(loop, d.loop_re+1j*d.loop_im)
    assert np.allclose(sensitivity, 1/(1+loop))
    assert not d.clipped.any(), 'Accepted clipping would invalidate this analysis.'
    # The measured crossover neighborhood has strong signals and no retained
    # clipping. Several excluded attempts elsewhere did hit real output rails.
    band = reliable & (f >= 3700) & (f <= 100000)
    predictions = {str(g): crossover(f[band], g*loop[band]) for g in (1.0, .5, .25)}
    injection = drive-error
    report = dict(source=str(SOURCE.relative_to(ROOT)),
        sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        points=len(d), reliable_points=int(reliable.sum()),
        first_reliable_frequency_hz=float(f[reliable][0]),
        tracking_gain_relative_to_stage3=float(d.tracking_coefficient.iloc[0]/104858),
        iir_enabled=bool(int(d.iir_control_word.iloc[0]) & 1),
        acquisition_stage=4 if int(d.acquisition_word.iloc[0]) & 8 else int(d.acquisition_word.iloc[0]) & 3,
        probe_amplitude_codes=int(d.amplitude_codes.iloc[0]),
        accepted_clipping_points=int(d.clipped.sum()),
        rejected_clipped_blocks=int(d.clipped_repeats.sum()),
        actual_dac_clip_samples_all_attempts=int(d.dac_clip_samples.sum()),
        internal_saturated_samples_all_attempts=int(d.detector_saturated_samples.sum()),
        max_injection_phasor_error_codes=float(abs(injection-d.amplitude_codes.to_numpy()).max()),
        conditional_gain_predictions=predictions,
        low_frequency_example=dict(frequency_hz=float(f[0]),
            residual_drive_codes=float(abs(drive[0])), drive_standard_error_codes=float(d.drive_stderr_codes.iloc[0])),
        limitations=['Only aggregate CSV supplied; individual accepted/rejected blocks cannot be re-examined.',
                     'Local phase margin assumes the linear negative-feedback convention L=-E/U.',
                     'Unreliable low-frequency ratios do not establish phase or global stability margins.',
                     'Gain-change prediction scales both feedback branches and assumes the plant is unchanged.',
                     'Clipping/slips rejected during acquisition can still indicate a nonstationary operating point.',
                     'A repeat at a second probe amplitude is needed to check linearity.'])
    OUTPUT.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n')

    plt.rcParams.update({'font.size': 10, 'axes.titlesize': 11})
    fig, axes = plt.subplots(3, 1, figsize=(10.8, 9), sharex=True, layout='constrained')
    phase = np.angle(loop, deg=True)
    phase = np.where(phase > 0, phase-360, phase)
    values = [20*np.log10(abs(loop)), phase, 20*np.log10(abs(sensitivity))]
    labels = ['Return-ratio magnitude (dB)', 'Loop phase (deg)', 'Sensitivity |1/(1+L)| (dB)']
    for ax, values_y, label in zip(axes, values, labels):
        ax.semilogx(f[~reliable], values_y[~reliable], 'x', color='.7', ms=5,
                    label='Fails repeat/SNR criteria')
        ax.semilogx(f, np.where(reliable, values_y, np.nan), '.-', color='#1769aa',
                    lw=1.4, ms=5, label='Accepted measurement')
        ax.axvspan(1000, report['first_reliable_frequency_hz'], color='.7', alpha=.1)
        ax.set_ylabel(label); ax.grid(alpha=.23, which='both')
    axes[0].semilogx(f[band], 20*np.log10(abs(loop[band])*.5), '--', color='#34836e',
                     label='Prediction: feedback gain ×0.5')
    axes[2].semilogx(f[band], 20*np.log10(abs(1/(1+.5*loop[band]))), '--', color='#34836e',
                     label='Prediction: feedback gain ×0.5')
    for ax in (axes[0], axes[2]):
        ax.axhline(0, color='.3', ls=':', lw=1)
    axes[1].axhline(-180, color='.3', ls=':', lw=1)
    for key, color in [('1.0', '#1769aa'), ('0.5', '#34836e')]:
        p = predictions[key]
        for ax in axes:
            ax.axvline(p['crossover_hz'], color=color, alpha=.5, ls=':')
        axes[1].plot(p['crossover_hz'], p['phase_at_crossover_deg'], 'o', color=color)
    axes[0].set(ylim=(-35, 48), title='Main crossover: 32.2 kHz; half-gain prediction: 20.0 kHz')
    axes[1].set(ylim=(-230, -90), title='Local phase margin: 28.3° measured; 35.1° predicted at half gain')
    axes[2].set(ylim=(-35, 10), title='Sensitivity peak: +6.7 dB measured; about +5.1 dB at half gain',
                xlabel='Test frequency (Hz)', xlim=(1000, 200000))
    for ax in (axes[0], axes[2]):
        ax.legend(fontsize=9, loc='lower left')
    fig.suptitle('Measured FPGA laser-loop FRA: stage 4, detector gain 2× (/80), IIR bypassed\n'
                 'Phase branch chosen near crossover; noisy low-frequency points are excluded', fontsize=12)
    fig.supxlabel('Dashed curves are predictions, not new measurements. '
                  'Rejected clipped blocks are excluded from plotted phasors; small-signal linearity remains to be checked.', fontsize=9)
    for ext in ('png', 'pdf'):
        fig.savefig(OUTPUT.with_suffix('.'+ext), dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
