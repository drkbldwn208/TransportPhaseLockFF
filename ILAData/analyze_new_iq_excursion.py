"""Inspect phase excursion in a saved FPGA I/Q record.

Pass an optional NPZ filename; the default is the first 240 kS/s record.

Unwrap assumes <pi true phase motion between adjacent recorded samples.
Hardware boxcar averaging precedes this atan2; near-zero averaged vectors and
large sample-to-sample rotations make the apparent winding count ambiguous.
No drift is removed when checking the FRA's range relative to arm.
"""
from pathlib import Path
import hashlib
import json
import os
import sys

os.environ.setdefault('MPLCONFIGDIR', '/tmp/new_iq_excursion_mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'10-13-IQ'
SOURCE = OUT/'laser_iq_FPGA.npz'


def envelope(time_s, values, block_samples=256):
    """Preserve block extrema in long plots instead of skipping narrow events."""
    count = len(values)//block_samples
    values = values[:count*block_samples].reshape(count, block_samples)
    times = time_s[:count*block_samples].reshape(count, block_samples).mean(axis=1)
    return times, values.min(axis=1), values.max(axis=1), values.mean(axis=1)


def main(source=SOURCE):
    source = Path(source).resolve()
    output_stem = source.with_name(source.stem+'_phase_excursion')
    with np.load(source, allow_pickle=False) as data:
        z = data['i_adc_counts']+1j*data['q_adc_counts']
        fs_hz = float(data['sample_rate_hz'])
        decimation = int(data['decimation_log2'])
    assert z.ndim == 1 and np.isfinite(z).all() and (abs(z) > 0).all()
    assert fs_hz == 245760000/(1 << decimation)
    time_s = np.arange(len(z))/fs_hz
    amplitude = abs(z)
    median_amplitude = np.median(amplitude)
    wrapped_rad = np.angle(z)
    phase_rad = np.unwrap(wrapped_rad)
    phase_rad -= phase_rad[0]
    turns = phase_rad/(2*np.pi)
    step_rad = np.angle(z[1:]*np.conj(z[:-1]))
    # Independent identities check conventions and numpy's branch selection.
    assert np.allclose(np.diff(phase_rad), step_rad, atol=1e-10)
    assert np.allclose(np.exp(1j*(phase_rad+wrapped_rad[0])), z/amplitude)
    crosses = np.flatnonzero(abs(turns) >= 2)
    block_samples = round(.005*fs_hz)
    n = len(z)//block_samples
    unit_vectors = (z/amplitude)[:n*block_samples].reshape(n, block_samples)
    resultant = abs(unit_vectors.mean(axis=1))
    # Standard circular spread; equals Gaussian sigma only under that model.
    circular_spread_rad = np.sqrt(-2*np.log(resultant))
    block_time_s = (np.arange(n)+.5)*block_samples/fs_hz
    overall_spread = float(np.sqrt(-2*np.log(abs(np.mean(z/amplitude)))))

    alternatives = []
    for average in (1, 2, 4):
        q = z[:len(z)//average*average].reshape(-1, average).mean(axis=1)
        p = np.unwrap(np.angle(q))/(2*np.pi)
        alternatives.append(dict(extra_iq_average=average, sample_rate_hz=fs_hz/average,
                                 apparent_span_turns=float(np.ptp(p)),
                                 apparent_net_turns=float(p[-1]-p[0])))
    # Separate sustained baseband magnitude collapses from isolated small vectors.
    amplitude_block = round(.001*fs_hz)
    count = len(z)//amplitude_block
    block_amplitude = amplitude[:count*amplitude_block].reshape(count, amplitude_block).mean(axis=1)/median_amplitude
    edges = np.diff(np.r_[False, block_amplitude < .2, False].astype(int))
    low_intervals = []
    for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
        if end-start >= 2:
            low_intervals.append(dict(start_s=start*amplitude_block/fs_hz,
                end_s=end*amplitude_block/fs_hz, duration_s=(end-start)*amplitude_block/fs_hz,
                mean_magnitude_fraction=float(block_amplitude[start:end].mean())))
    summary = dict(source=str(source.relative_to(ROOT)),
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        conditions='Previous record: user confirmed 800 MHz beat/reference and FRA off. '
                   'Other records assumed to use that setup; NPZ does not save these settings.',
        samples=len(z), sample_rate_hz=fs_hz, decimation_log2=decimation,
        duration_s=len(z)/fs_hz,
        apparent_phase_min_turns=float(turns.min()), apparent_phase_max_turns=float(turns.max()),
        apparent_phase_span_turns=float(np.ptp(turns)), apparent_net_turns=float(turns[-1]),
        apparent_phase_span_rad=float(np.ptp(phase_rad)),
        apparent_first_two_turn_crossing_s=float(time_s[crosses[0]]) if len(crosses) else None,
        amplitude_median_adc_counts=float(median_amplitude),
        amplitude_min_adc_counts=float(amplitude.min()),
        amplitude_fractional_std=float(amplitude.std()/amplitude.mean()),
        fraction_amplitude_below_20_percent_median=float(np.mean(amplitude < .2*median_amplitude)),
        phase_step_over_pi_half_fraction=float(np.mean(abs(step_rad) > np.pi/2)),
        phase_step_over_0p9pi_count=int(np.sum(abs(step_rad) > .9*np.pi)),
        phase_step_max_rad=float(abs(step_rad).max()),
        circular_spread_rad=overall_spread,
        five_ms_circular_spread_percentiles_rad=np.percentile(circular_spread_rad, [5, 50, 95, 100]).tolist(),
        extra_averaging_sensitivity=alternatives,
        sustained_low_magnitude_intervals=low_intervals,
        limitations=['Apparent unwrap is not a verified physical cycle-slip count.',
                     'Decimation/complex averaging precedes atan2; high-frequency phase motion can be missed.',
                     'Low averaged amplitude may reflect cancellation from phase motion, not RF amplitude loss.',
                     'This separate record does not identify which ORed FRA saturation source fired.',
                     'Circular spread is not an unwrapped RMS phase measurement.',
                     'No drift subtraction or phase-noise integration used.'])
    output_stem.with_suffix('.json').write_text(json.dumps(summary, indent=2)+'\n')

    plt.rcParams.update({'font.size': 10, 'axes.titlesize': 11})
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout='constrained')
    t, lo, hi, mean = envelope(time_s, turns)
    axes[0, 0].fill_between(t, lo, hi, color='#1769aa', alpha=.3)
    axes[0, 0].plot(t, mean, color='#1769aa', lw=1)
    axes[0, 0].set(title=f'Naive unwrap: {np.ptp(turns):.1f}-turn span; winding count is ambiguous',
                   ylabel='Apparent phase relative to first sample (turns)', xlabel='Time (s)')
    crossing_s = summary['apparent_first_two_turn_crossing_s']
    zoom_s = min(time_s[-1], max(.1, min(.5, 1.5*crossing_s))) if crossing_s else min(.1,time_s[-1])
    mask = time_s < zoom_s
    axes[0, 1].plot(time_s[mask]*1000, turns[mask], color='#1769aa', lw=.65)
    for bound in (-2, 2):
        axes[0, 1].axhline(bound, color='#c35b25', ls='--', lw=1)
    crossing_text = f'±2-turn crossing at {1000*crossing_s:.2f} ms' if crossing_s else 'No ±2-turn crossing'
    axes[0, 1].set(title=f'Initial {1000*zoom_s:.0f} ms: apparent {crossing_text}',
                   ylabel='Apparent phase relative to first sample (turns)', xlabel='Time (ms)')
    t, lo, hi, mean = envelope(time_s, amplitude/median_amplitude)
    axes[1, 0].fill_between(t, lo, hi, color='#34836e', alpha=.3,
                           label=f'Min–max per {256/fs_hz*1000:.2f} ms')
    axes[1, 0].plot(t, mean, color='#34836e', lw=1, label='Mean')
    axes[1, 0].axhline(.2, color='#c35b25', ls='--', lw=.8)
    axes[1, 0].set(title='Averaged I/Q magnitude occasionally approaches zero',
                   ylabel='Magnitude / median magnitude', xlabel='Time (s)',
                   ylim=(0, 1.05*amplitude.max()/median_amplitude))
    axes[1, 0].legend(fontsize=8)
    axes[1, 1].plot(block_time_s, circular_spread_rad, color='#655095', lw=1)
    axes[1, 1].set(title='Circular phase spread in 5 ms windows; no unwrapping',
                   ylabel='√[−2 ln |mean(exp(iφ))|] (rad)', xlabel='Time (s)')
    for ax in axes.flat:
        ax.grid(alpha=.22)
    for interval in low_intervals:
        if interval['duration_s'] >= .01:
            for ax in (axes[0, 0], axes[1, 0], axes[1, 1]):
                ax.axvspan(interval['start_s'], interval['end_s'], color='#c35b25', alpha=.12)
    large_steps_percent = summary['phase_step_over_pi_half_fraction']*100
    fig.suptitle(f'{source.name}: {fs_hz/1000:g} kS/s, {len(z)/fs_hz:.3f} s\n'
                 f'{large_steps_percent:.2f}% of adjacent phase steps exceed π/2; '
                 'low-rate unwrap cannot reliably count every turn', fontsize=12)
    fig.supxlabel('Dashed ±2 turns illustrate the FRA range; this is a separately acquired, averaged I/Q record. '
                  'The apparent winding count is not a measurement of RMS phase noise.', fontsize=9)
    for ext in ('png', 'pdf'):
        fig.savefig(output_stem.with_suffix('.'+ext), dpi=180)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else SOURCE)
