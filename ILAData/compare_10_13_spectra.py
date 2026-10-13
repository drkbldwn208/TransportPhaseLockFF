"""Compare 13 October RF beat spectra; these are display traces, not phase PSDs.

Keep native-RBW line heights separate from an approximate broadband proxy
P_display - P_carrier - 10*log10(RBW/Hz). The positive-peak detector, sparse
display buckets and incomplete-sweep flags preclude integrating this as S_phi.
No source CSV is modified. Run this file to regenerate the PNG/PDF and JSON.
"""
from pathlib import Path
import json
import os
import numpy as np

os.environ.setdefault('MPLCONFIGDIR', '/tmp/spectra_10_13_matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.signal import find_peaks

from compare_adf_fpga_lock import load_trace

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '10-13SpectrumAnalyzer'
COLORS = ['#1769aa', '#c85a26', '#27806b']
BANDS_KHZ = [(10, 30), (30, 60), (60, 100), (100, 200),
             (200, 300), (300, 400), (400, 500)]


def label(trace):
    meta = trace['metadata']
    return f"{Path(meta['file']).stem.removeprefix('File_')} · RBW {meta['rbw_hz']:g} Hz"


def draw(ax, trace, field, name, color, **kwargs):
    ax.plot(trace['offset_hz']/1e3, trace[field], label=name, color=color, **kwargs)


def describe(trace):
    x, y = trace['offset_hz'], trace['relative_dbc']
    peaks, _ = find_peaks(y, prominence=4, distance=2)
    strongest = sorted((i for i in peaks if abs(x[i]) > 3000),
                       key=lambda i: y[i], reverse=True)[:12]
    bands = []
    for low, high in BANDS_KHZ:
        selected = (abs(x) >= low*1000) & (abs(x) < high*1000)
        if not selected.any():
            continue
        bands.append(dict(low_hz=low*1000, high_hz=high*1000,
            display_points=int(selected.sum()),
            median_native_dbc=float(np.median(y[selected])),
            median_density_proxy_db=float(np.nanmedian(trace['density_proxy'][selected]))))
    return dict(metadata=trace['metadata'], bands=bands,
                strongest_displayed_features=[dict(offset_hz=float(x[i]),
                    native_dbc=float(y[i])) for i in strongest])


def main():
    traces = [load_trace(f'10-13SpectrumAnalyzer/File_{name}.csv')
              for name in ['0W', '0WNS', '0WNS2']]
    assert all(len(t['offset_hz']) == 401 for t in traces)
    assert all(np.allclose(t['offset_hz'], traces[0]['offset_hz']) for t in traces)
    plt.rcParams.update({'font.size': 10, 'axes.titlesize': 11})
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), layout='constrained')
    for t, color in zip(traces, COLORS):
        draw(axes[0, 0], t, 'power_dbm', label(t), color, lw=1.0)
        draw(axes[0, 1], t, 'relative_dbc', label(t), color, lw=1.0, marker='.', ms=3)
        draw(axes[1, 0], t, 'density_proxy', label(t), color, lw=1.0)
        draw(axes[1, 1], t, 'density_proxy', label(t), color, lw=1.0, marker='.', ms=2.5)
    axes[0, 0].set(xlim=(-510, 510), ylim=(-92, -24), ylabel='Displayed power (dBm)',
                   title='Recorded RF power; WNS2 has a wider RBW')
    axes[0, 1].set(xlim=(-115, 115), ylim=(-53, 3), ylabel='Carrier-relative level (dBc)',
                   title='Line heights at native RBW; 2.54 kHz display spacing')
    axes[1, 0].set(xlim=(-510, 510), ylim=(-67, -20),
                   ylabel='Relative level − 10 log₁₀(RBW/Hz) (dB)',
                   title='Approximate broadband comparison; not a phase PSD')
    axes[1, 1].set(xlim=(180, 450), ylim=(-64, -20),
                   ylabel='Relative level − 10 log₁₀(RBW/Hz) (dB)',
                   title='300–400 kHz shoulder and isolated +252 kHz feature')
    axes[1, 1].axvspan(300, 400, color='gray', alpha=.07)
    for ax in axes.flat:
        ax.set_xlabel('Offset from displayed carrier peak (kHz)')
        ax.grid(alpha=.22)
        ax.legend(fontsize=9)
    fig.suptitle('13 October 2026 beat spectra · 800 MHz carrier\n'
                 'W / WNS / WNS2 filenames retained; acquisition settings not yet identified', fontsize=13)
    fig.supxlabel('Positive-peak detector, one sweep; all files flag an incomplete sweep. '
                  'Nominal RBW correction omits ENBW and detector bias.', fontsize=9)
    for extension in ['png', 'pdf']:
        fig.savefig(OUT / f'spectra_10_13.{extension}', dpi=180)
    plt.close(fig)

    old = [load_trace(name) for name in ['File_0BEST.csv', 'File_0_ADF4108_Loop.csv',
                                         'File_01_ADF4108_Loop.csv']]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), layout='constrained')
    # W and WNS show nearly identical low-offset backgrounds. Use W as the
    # representative 3 Hz scan and show WNS2 to expose run-to-run variation.
    for ax in axes:
        for t, color in [(traces[0], COLORS[0]), (traces[2], COLORS[2])]:
            draw(ax, t, 'density_proxy', '13 Oct '+label(t), color, lw=1)
    draw(axes[0], old[0], 'density_proxy', 'Earlier FPGA 8× · 10 Hz RBW', '#975aa6', lw=1)
    draw(axes[0], old[1], 'density_proxy', 'ADF4108 narrow · 3 Hz RBW', '#c85a26', lw=1)
    draw(axes[1], old[2], 'density_proxy', 'ADF4108 wide · 30 Hz RBW', '#c85a26', lw=1)
    axes[0].set(xlim=(-72, 72), title='Close-in comparison: display spacings differ')
    axes[1].set(xlim=(-510, 510), title='Wide comparison: similar high-offset shoulder')
    for ax in axes:
        ax.set(ylim=(-68, -18), xlabel='Offset from displayed carrier peak (kHz)',
               ylabel='Relative level − 10 log₁₀(RBW/Hz) (dB)')
        ax.grid(alpha=.22)
        ax.legend(fontsize=8, loc='lower left')
    fig.suptitle('New RF spectra against prior FPGA and ADF4108 records', fontsize=13)
    fig.supxlabel('Approximate broadband comparison only. Independently aligned carriers; '
                  'unequal RBWs, bucket widths and carrier levels. No integrated RMS inferred.', fontsize=9)
    for extension in ['png', 'pdf']:
        fig.savefig(OUT / f'spectra_10_13_baselines.{extension}', dpi=180)
    plt.close(fig)

    summary = dict(traces=[describe(t) for t in traces], baselines=[describe(t) for t in old],
        rbw_10_vs_3_hz_noise_change_db=float(10*np.log10(10/3)),
        offset_convention='Subtract displayed carrier peak frequency, not nominal center. '
                          'Peak display coordinate can differ from the true carrier by a bucket.',
        limitations=['AM and PM cannot be separated from RF power alone.',
                     'Sparse positive-peak display buckets are not uniformly sampled PSD values.',
                     'Native line powers and broadband RBW-normalized levels are distinct metrics.',
                     'All input records flag an incomplete sweep; repeat in single-sweep mode.',
                     'No independently measured open-loop gain or free-running baseline here; '
                     'a spectral shoulder does not establish loop crossover.',
                     'No integrated 1–10 kHz phase noise or linewidth inferred.'])
    (OUT / 'spectra_10_13_summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print('Wrote spectra_10_13{,_baselines}.{png,pdf} and spectra_10_13_summary.json')


if __name__ == '__main__':
    main()
