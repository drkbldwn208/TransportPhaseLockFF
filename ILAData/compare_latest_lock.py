"""Compare the new 8x/filter-tuned lock with saved FPGA and analog baselines.

Phase PSD CSV units are rad^2/Hz. Integrate common bands; do not compare narrow
peak heights across unequal FFT windows. RF traces retain their native RBWs;
RBW-normalized curves are only broadband-density proxies for positive detection.
"""
from pathlib import Path
import hashlib
import json
import os
os.environ.setdefault('MPLCONFIGDIR', '/tmp/latest_lock_matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
COLORS = ['#63666a', '#2077b4', '#bf462a']
NAMES = ['Analog detector, Oct 5', 'FPGA, Oct 9', 'FPGA 8×, retuned filters']


def band_variance(f_hz, phase_psd, low_hz, high_hz):
    selected = (f_hz >= low_hz) & (f_hz < high_hz)
    return float(phase_psd[selected].sum()*(f_hz[1]-f_hz[0]))


def load_rf(filename):
    path = ROOT/filename
    lines = path.read_text().splitlines()
    data = np.array([[float(x) for x in line.split(',')[:2]]
                     for line in lines[lines.index('BEGIN')+1:] if line and line != 'END'])
    f_hz, dbm = data.T
    def number(key):
        return float(next(line.split()[-1] for line in lines if key in line))
    peak = int(np.argmax(dbm))
    metadata = dict(file=filename, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        rbw_hz=number('ResolutionBW'), vbw_hz=number('VideoBW'),
        internal_attenuation_db=number('RF Attenuation'),
        point_spacing_hz=float(np.median(np.diff(f_hz))),
        peak_dbm=float(dbm[peak]), peak_frequency_hz=float(f_hz[peak]),
        detector='Positive', incomplete_sweep_warning=True)
    return dict(f=f_hz, dbm=dbm, metadata=metadata)


def main():
    old_path = ROOT/'laser_lock_psd_comparison.csv'
    new_path = ROOT/'laser_phase_psd_20261012_020456.csv'
    old = np.genfromtxt(old_path, delimiter=',', names=True)
    new_f, new_p = np.loadtxt(new_path, delimiter=',', skiprows=1).T
    assert np.all(np.isfinite(new_p)) and np.all(new_p >= 0)
    assert np.allclose(np.diff(new_f), new_f[1])
    records = [(old['frequency_Hz'], old['old_phase_rad2_per_Hz']),
               (old['frequency_Hz'], old['new_phase_rad2_per_Hz']), (new_f, new_p)]
    bands = [(234.375, 1000), (1000, 10000), (10000, 100000),
             (100000, 200000), (170000, 180000), (200000, 400000),
             (40000, 60000), (234.375, 200000), (234.375, 400000)]
    comparison = []
    for low, high in bands:
        powers = [band_variance(f, p, low, high) for f, p in records]
        comparison.append(dict(low_hz=low, high_hz=high,
            rms_phase_rad=dict(zip(NAMES, np.sqrt(powers).tolist())),
            latest_vs_analog_db=float(10*np.log10(powers[2]/powers[0])),
            latest_vs_oct9_fpga_db=float(10*np.log10(powers[2]/powers[1]))))

    plt.rcParams.update({'font.size': 10, 'axes.titlesize': 11})
    fig = plt.figure(figsize=(12, 8), layout='constrained')
    grid = fig.add_gridspec(2, 2)
    top = fig.add_subplot(grid[0, :])
    cumulative = fig.add_subplot(grid[1, 0])
    zoom = fig.add_subplot(grid[1, 1])
    for (f, p), name, color in zip(records, NAMES, COLORS):
        top.loglog(f[1:], p[1:], color=color, lw=.8, label=name)
        mask = (f >= 234.375) & (f <= 400000)
        cumulative.semilogx(f[mask], np.sqrt(np.cumsum(p[mask])*(f[1]-f[0])),
                            color=color, label=name)
        zoom.semilogy(f/1000, p, color=color, lw=.8)
    top.set(xlim=(234.375, 400000), ylim=(1e-9, .05),
            xlabel='Fourier frequency (Hz)', ylabel='Phase PSD (rad²/Hz)',
            title='Latest close-in suppression improves; 40–60 kHz modulation now dominates')
    top.legend(loc='upper right')
    cumulative.set(xlabel='Upper integration frequency (Hz)', ylabel='Integrated phase RMS (rad)',
                   title='Integration starts at 234.375 Hz', xlim=(234.375, 400000), ylim=(0, 3.5))
    zoom.set(xlabel='Fourier frequency (kHz)', ylabel='Phase PSD (rad²/Hz)',
             title='Remaining 40–60 kHz feature', xlim=(35, 65), ylim=(1e-8, .02))
    for ax in (top, cumulative, zoom):
        ax.grid(True, which='both', alpha=.25)
    fig.suptitle('Phase-noise comparison with and without the FPGA detector\n'
        'Latest PSD: 7.32 Hz bins; baselines: 234.375 Hz bins. Compare integrated bands, not line heights.', fontsize=12)
    fig.savefig(ROOT/'latest_lock_phase_comparison.png', dpi=180)
    fig.savefig(ROOT/'latest_lock_phase_comparison.pdf')
    plt.close(fig)

    # Narrow traces locate the old carriers more accurately than wide traces.
    rf1, rf4, best = [load_rf(name) for name in ('File_01x.csv', 'File_04x.csv', 'File_0BEST.csv')]
    wide1, wide4 = [load_rf(name) for name in ('File_01xW.csv', 'File_04xW.csv')]
    groups = [(rf1, wide1, 'Previous 1×', '#2077b4'),
              (rf4, wide4, 'Previous 4×', '#d59a19'),
              (best, best, 'Latest 8× / new filters', '#bf462a')]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
    for narrow, wide, name, color in groups:
        carrier_hz = narrow['metadata']['peak_frequency_hz']
        for ax, trace, relative, normalize in (
                (axes[0, 0], narrow, False, False),
                (axes[0, 1], narrow, True, False),
                (axes[1, 0], wide, True, False),
                (axes[1, 1], wide, True, True)):
            # Each relative trace uses its own displayed carrier peak: no mixing
            # carrier levels from separate narrow/wide acquisitions.
            level = trace['dbm'].copy()
            if relative:
                level -= trace['metadata']['peak_dbm']
            if normalize:
                level -= 10*np.log10(trace['metadata']['rbw_hz'])
                # An unresolved carrier is tone power, not broadband density.
                level[abs(trace['f']-carrier_hz) < 2*trace['metadata']['point_spacing_hz']] = np.nan
            label = f"{name}: RBW {trace['metadata']['rbw_hz']:g} Hz"
            ax.plot((trace['f']-carrier_hz)/1000, level, '.-', color=color,
                    lw=1, ms=2.5, label=label)
    axes[0, 0].set(xlim=(-3, 3), xlabel='Offset from displayed carrier (kHz)',
        ylabel='Native trace level (dBm)', title='Absolute levels; RF levels and RBWs may differ')
    axes[0, 1].set(xlim=(-3, 3), xlabel='Offset from displayed carrier (kHz)',
        ylabel='Native trace / carrier (dBc)', title='Close-in pedestal: latest trace has 359 Hz spacing')
    axes[1, 0].set(xlim=(-70, 70), xlabel='Offset from displayed carrier (kHz)',
        ylabel='Native trace / carrier (dBc)', title='Wide-span sidebands; native RBWs retained')
    axes[1, 1].set(xlim=(-70, 70), xlabel='Offset from displayed carrier (kHz)',
        ylabel='Carrier-relative level − 10 log₁₀(RBW/Hz)',
        title='Approximate broadband density comparison')
    axes[1, 1].text(.02, .02, 'Not calibrated phase noise; narrow-line heights are RBW dependent.',
                   transform=axes[1, 1].transAxes, fontsize=8)
    for ax in axes.flat:
        ax.grid(alpha=.25); ax.legend(fontsize=8)
    fig.suptitle('Measured RF beat spectra: each carrier aligned to zero offset\n'
        'All traces: positive-peak detector, one sweep, incomplete-sweep flag. Dots show actual display samples.', fontsize=12)
    fig.savefig(ROOT/'latest_lock_rf_comparison.png', dpi=180)
    fig.savefig(ROOT/'latest_lock_rf_comparison.pdf')
    plt.close(fig)

    total_variance = float(new_p.sum()*new_f[1])
    summary = dict(latest_file=new_path.name,
        latest_sha256=hashlib.sha256(new_path.read_bytes()).hexdigest(),
        baseline_table=old_path.name,
        baseline_table_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest(),
        operating_point='User confirmed 8x phase gain and substantially changed analog loop filters.',
        latest_bin_spacing_hz=float(new_f[1]), latest_nyquist_hz=float(new_f[-1]),
        latest_total_recorded_rms_rad=float(np.sqrt(total_variance)),
        fraction_variance_40_60_khz=band_variance(new_f, new_p, 40000, 60000)/total_variance,
        comparison=comparison,
        rf_traces=[r['metadata'] for r in (rf1, rf4, wide1, wide4, best)],
        limitations=[
            'Latest raw I/Q absent: cannot verify unwrapping, transient phase slips, or amplitude dropouts.',
            'Latest saved PSD uses finer Welch bins; broad-band integrals are compared, not narrow peak heights.',
            'Old analog and FPGA receiver filters, record durations and operating points differ.',
            'Do not attribute all improvements specifically to FPGA: analog filters/gains changed too.',
            'RF carrier level changed; RF attenuation/connection history awaits user confirmation.',
            'RBW-normalized RF curves are positive-peak broadband proxies, not calibrated phase PSD.',
            'There is no matched RF-analyzer trace of the confirmed analog baseline; use its I/Q phase PSD.'])
    (ROOT/'latest_lock_comparison.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
