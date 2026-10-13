"""Compare Oct 11 /160 and /40 locks using I/Q and independent RF traces.

I/Q is a boxcar-averaged complex envelope, not a sample of unaveraged phase.
Unwrap diagnostics therefore accompany every phase PSD. The RF analyzer used
positive-peak detection and incomplete sweeps: compare features and carrier
levels, not calibrated integrated phase variance. Raw files remain unchanged.
"""
from pathlib import Path
import hashlib
import json
import os

os.environ.setdefault('MPLCONFIGDIR', '/tmp/phase_gain_matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parent
COLORS = ['#1769aa', '#d45a24']
NSEG = 262144
BANDS = [(20, 100), (100, 1000), (1000, 10000), (10000, 100000),
         (100000, 200000), (200000, 900000)]


def welch(x, fs_hz, detrend='constant', nseg=NSEG):
    return signal.welch(x, fs=fs_hz, window='hann', nperseg=nseg,
                        noverlap=nseg//2, detrend=detrend, scaling='density',
                        return_onesided=not np.iscomplexobj(x))


def band_power(f_hz, density, low_hz, high_hz):
    mask = (abs(f_hz) >= low_hz) & (abs(f_hz) < high_hz)
    return float(density[mask].sum() * (f_hz[1]-f_hz[0]))


def parseval_check(x, fs_hz, density):
    window = signal.windows.hann(NSEG, sym=False)
    segments = np.lib.stride_tricks.sliding_window_view(x, NSEG)[::NSEG//2]
    segments = segments - segments.mean(axis=1, keepdims=True)
    expected = np.mean(np.sum(abs(segments*window)**2, axis=1)/np.sum(window**2))
    assert np.isclose(np.sum(density)*fs_hz/NSEG, expected, rtol=1e-10)


def iq_record(filename, gain):
    path = ROOT/filename
    with np.load(path) as data:
        z = data['i_adc_counts'] + 1j*data['q_adc_counts']
        fs_hz = float(data['sample_rate_hz'])
        decimation = int(data['decimation_log2'])
    assert np.all(np.isfinite(z)) and np.min(abs(z)) > 0
    amplitude = abs(z)
    phase = np.unwrap(np.angle(z))
    phase_residual = signal.detrend(phase)
    am = amplitude/amplitude.mean()-1
    unit = z/amplitude
    normalized = z/np.sqrt(np.mean(amplitude**2))
    f_hz, phase_psd = welch(phase_residual, fs_hz)
    _, am_psd = welch(am, fs_hz)
    envelope_f_hz, envelope_psd = welch(normalized, fs_hz)
    _, phase_only_psd = welch(unit, fs_hz)
    parseval_check(phase_residual, fs_hz, phase_psd)
    parseval_check(normalized, fs_hz, envelope_psd)
    coherent_fraction = float(abs(normalized.mean())**2)
    steps = np.angle(z[1:]*z[:-1].conj())
    statistics = dict(
        file=filename, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        gain=gain, samples=len(z), sample_rate_hz=fs_hz, decimation_log2=decimation,
        duration_s=len(z)/fs_hz, bin_spacing_hz=fs_hz/NSEG,
        welch_segments=1+(len(z)-NSEG)//(NSEG//2),
        mean_amplitude_adc_counts=float(amplitude.mean()),
        fractional_amplitude_rms=float(am.std()),
        minimum_amplitude_relative_to_mean=float(amplitude.min()/amplitude.mean()),
        coherent_power_fraction=coherent_fraction,
        coherent_carrier_adc_counts_squared=float(abs(z.mean())**2),
        phase_only_coherent_power_fraction=float(abs(unit.mean())**2),
        apparent_phase_rms_rad=float(phase_residual.std()),
        apparent_net_turns=float((phase[-1]-phase[0])/(2*np.pi)),
        phase_steps_over_pi_over_2=int(np.count_nonzero(abs(steps)>np.pi/2)),
        phase_steps_over_0p9pi=int(np.count_nonzero(abs(steps)>.9*np.pi)),
        bands={})
    # Interpolation cannot undo aliasing or boxcar averaging. Sensitivity of
    # inferred winding count to bandlimited interpolation diagnoses ambiguity.
    statistics['interpolation_unwrap_diagnostic'] = {}
    for factor in (2, 4, 8):
        interpolated = signal.resample_poly(z, factor, 1)
        interp_phase = np.unwrap(np.angle(interpolated))[::factor][:len(z)]
        difference_turns = (interp_phase-phase)/(2*np.pi)
        statistics['interpolation_unwrap_diagnostic'][str(factor)] = dict(
            net_turns=float((interp_phase[-1]-interp_phase[0])/(2*np.pi)),
            detrended_rms_rad=float(signal.detrend(interp_phase).std()),
            min_difference_turns=float(difference_turns.min()),
            max_difference_turns=float(difference_turns.max()))
    for low, high in BANDS:
        statistics['bands'][f'{low:g}-{high:g} Hz'] = dict(
            apparent_phase_rms_rad=np.sqrt(band_power(f_hz, phase_psd, low, high)),
            envelope_power_fraction=band_power(envelope_f_hz, envelope_psd, low, high),
            phase_only_envelope_power=band_power(envelope_f_hz, phase_only_psd, low, high))
    # Examine coherent-carrier stability across 65 ms subrecords.
    length = 125000
    statistics['subrecord_coherent_fraction'] = [
        float(abs(v.mean())**2/np.mean(abs(v)**2)) for v in z.reshape(-1, length)]
    for low, high in ((370, 480), (165000, 185000), (330000, 370000)):
        statistics[f'envelope_power_{low}_{high}_Hz'] = band_power(
            envelope_f_hz, envelope_psd, low, high)
    np.savez_compressed(ROOT/f'phase_gain_{gain}x_spectra.npz',
        frequency_hz=f_hz, apparent_phase_psd_rad2_per_hz=phase_psd,
        fractional_amplitude_psd_per_hz=am_psd,
        envelope_frequency_hz=envelope_f_hz,
        envelope_psd_per_hz=envelope_psd, phase_only_envelope_psd_per_hz=phase_only_psd)
    return dict(z=z, phase=phase, phase_residual=phase_residual, f=f_hz,
                pp=phase_psd, aa=am_psd, ef=envelope_f_hz, ep=envelope_psd,
                po=phase_only_psd, fs=fs_hz, gain=gain, stats=statistics)


def analyzer_trace(filename):
    path = ROOT/filename
    lines = path.read_text().splitlines()
    begin = lines.index('BEGIN')
    data = np.array([[float(v) for v in row.split(',')[:2]]
                     for row in lines[begin+1:] if row and row != 'END'])
    f_hz, dbm = data.T
    rbw_hz = float(next(s.split()[-1] for s in lines if 'ResolutionBW' in s))
    carrier_index = np.argmax(dbm)
    stats = dict(file=filename, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                 rbw_hz=rbw_hz, point_spacing_hz=float(np.median(np.diff(f_hz))),
                 detector='Positive', averages=1, incomplete_sweep_warning=True,
                 peak_frequency_hz=float(f_hz[carrier_index]),
                 peak_dbm=float(dbm[carrier_index]))
    return dict(f=f_hz, dbm=dbm, stats=stats)


def make_figures(records, traces):
    plt.rcParams.update({'font.size': 10, 'axes.titlesize': 11})
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
    for r, color in zip(records, COLORS):
        f = r['f']; label = f"{r['gain']}× phase gain"
        axes[0, 0].loglog(f[1:], r['pp'][1:], color=color, label=label, lw=.7)
        fold = r['ep'][:NSEG//2+1].copy()
        fold[1:-1] += r['ep'][:NSEG//2:-1]
        fold_po = r['po'][:NSEG//2+1].copy()
        fold_po[1:-1] += r['po'][:NSEG//2:-1]
        axes[0, 1].semilogx(f[1:], 10*np.log10(fold[1:]), color=color, label=label, lw=.8)
        axes[0, 1].semilogx(f[1:], 10*np.log10(fold_po[1:]), color=color, ls=':', lw=.6)
        time_s = np.arange(len(r['z']))/r['fs']
        axes[1, 0].plot(time_s[::100], r['phase'][::100]/(2*np.pi), color=color, lw=.5, label=label)
        axes[1, 1].loglog(f[1:], r['aa'][1:], color=color, lw=.7, label=label)
    axes[0, 0].set(title='Apparent unwrapped phase: winding count is ambiguous',
                    xlabel='Fourier frequency (Hz)', ylabel='Phase PSD (rad²/Hz)', xlim=(10, 960000))
    axes[0, 1].set(title='Complex-envelope PSD does not require unwrapping',
                    xlabel='Offset frequency (Hz)', ylabel='Folded envelope PSD (dB/Hz)', xlim=(10, 960000))
    axes[0, 1].text(.03, .05, 'Solid: full I/Q; dotted: amplitude normalized\nPower normalized to total recorded envelope power',
                    transform=axes[0, 1].transAxes, fontsize=8)
    axes[1, 0].set(xlabel='Time (s)', ylabel='Apparent unwrapped phase (turns)',
                   title='Direct angle unwrapping: not a proven optical slip count')
    axes[1, 1].set(xlabel='Fourier frequency (Hz)', ylabel='Fractional AM PSD (1/Hz)',
                   title='Recorded AM includes pre-arctan vector averaging', xlim=(10, 960000))
    for ax in axes.flat:
        ax.grid(True, which='both', alpha=.25); ax.legend(fontsize=9)
    fig.suptitle('October 11: /160 versus /40, FALC gain reduced for /40\n'
                 'Both I/Q records: 1.92 MS/s, 0.521 s, 7.32 Hz Welch bins', fontsize=12)
    fig.savefig(ROOT/'phase_gain_iq_comparison.png', dpi=180)
    fig.savefig(ROOT/'phase_gain_iq_comparison.pdf')
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
    for index, (r, color) in enumerate(zip(records, COLORS)):
        narrow, wide = traces[2*index:2*index+2]
        carrier_hz = narrow['stats']['peak_frequency_hz']
        label = f"{r['gain']}× phase gain"
        axes[0, 0].plot((narrow['f']-carrier_hz)/1000, narrow['dbm'], color=color, label=label, lw=1)
        axes[0, 1].plot((wide['f']-carrier_hz)/1000, wide['dbm'], color=color, label=label, lw=1)
        order = np.argsort(r['ef'])
        density = r['ep'][order]/r['stats']['coherent_power_fraction']
        f_hz = r['ef'][order]
        for ax in axes[1]:
            ax.plot(f_hz/1000, 10*np.log10(density), color=color, lw=.7, label=label)
    axes[0, 0].set(title='RF analyzer: RBW 1 Hz, positive-peak detector',
                    ylabel='Displayed power (dBm)', xlim=(-10, 10))
    axes[0, 1].set(title='RF analyzer: RBW 30 Hz, positive-peak detector',
                    ylabel='Displayed power (dBm)', xlim=(-620, 620))
    axes[1, 0].set(title='I/Q sideband density relative to coherent carrier',
                    ylabel='Envelope sidebands (dBc/Hz)', xlim=(-10, 10), ylim=(-100, -15))
    axes[1, 1].set(title='I/Q: broad noise and narrow spectral lines',
                    ylabel='Envelope sidebands (dBc/Hz)', xlim=(-620, 620), ylim=(-100, -15))
    for ax in axes.flat:
        ax.set_xlabel('Offset from carrier (kHz)'); ax.grid(alpha=.25); ax.legend(fontsize=9)
    fig.suptitle('Independent RF spectra and complex I/Q spectra\n'
                 'Analyzer is aligned to each narrow-trace peak; vertical scales are not directly interchangeable', fontsize=12)
    fig.savefig(ROOT/'phase_gain_rf_comparison.png', dpi=180)
    fig.savefig(ROOT/'phase_gain_rf_comparison.pdf')
    plt.close(fig)


def main():
    records = [iq_record('laser_iq_20261011_184622.npz', 1),
               iq_record('laser_iq_20261011_184941.npz', 4)]
    traces = [analyzer_trace(name) for name in
              ('File_01x.csv', 'File_01xW.csv', 'File_04x.csv', 'File_04xW.csv')]
    make_figures(records, traces)
    summary = dict(iq=[r['stats'] for r in records], analyzer=[t['stats'] for t in traces],
        iq_coherent_carrier_change_db=float(10*np.log10(
            records[1]['stats']['coherent_carrier_adc_counts_squared'] /
            records[0]['stats']['coherent_carrier_adc_counts_squared'])),
        analyzer_narrow_carrier_change_db=traces[2]['stats']['peak_dbm']-traces[0]['stats']['peak_dbm'],
        nominal_phase_quantization_rad={
            'command_16bit_1x':160*2*np.pi/65536,
            'command_16bit_4x':40*2*np.pi/65536,
            'physical_14bit_1x':160*2*np.pi/16384,
            'physical_14bit_4x':40*2*np.pi/16384,
            'cordic_18bit_both':2*np.pi/262144},
        analog_change='User: only FALC gain reduced, roughly 4x, optimized by beat spectrum.',
        interpretation_limits=[
            'D7 averages rotating vectors before phase extraction; near-pi steps make unwrapping ambiguous.',
            'Interpolation checks sensitivity; they do not restore missing high-frequency information.',
            'Analyzer is positive-peak, one average, point spacing much wider than RBW, and flags incomplete sweeps.',
            'RF traces and I/Q records are not simultaneous; carrier peak comparison is approximate.',
            'In-loop noise is not an independent detector-noise-floor measurement.',
            'Both detector and analog gain changed: no isolated measurement of quantization improvement.'])
    (ROOT/'phase_gain_comparison.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
