"""Compare new FPGA/ADF beat spectra at their native analyzer resolution.

Input files are untouched. These are positive-peak display buckets, not phase
PSDs: nominal RBW correction is only an approximate broadband comparison.
Do not integrate the plotted curves to infer RMS optical phase noise.
"""
from pathlib import Path
import json

import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import median_filter

from compare_adf_fpga_lock import load_trace, strongest_lines

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '10-13SpectrumAnalyzer'
FILES = {
    'fpga_wide': '10-13SpectrumAnalyzer/File_0FPGAW.csv',
    'fpga_narrow': '10-13SpectrumAnalyzer/File_0FPGAN.csv',
    'adf_narrow': '10-13SpectrumAnalyzer/File_0PLLN.csv',
    'adf_wide_30hz': 'File_01_ADF4108_Loop.csv',
    'adf_wide_3hz': '10-13SpectrumAnalyzer/File_0PLL.csv',
    'previous_fpga_wide': '10-13SpectrumAnalyzer/File_0W.csv',
}
BANDS_KHZ = [(1, 10), (10, 30), (40, 60), (60, 100), (100, 200),
             (200, 300), (300, 400), (400, 500)]
COLORS = {'fpga_wide': '#1769aa', 'adf_wide_30hz': '#c35b25',
          'adf_wide_3hz': '#34836e'}
LABELS = {'fpga_wide': 'New FPGA wide · RBW 10 Hz',
          'adf_wide_30hz': 'Earlier ADF wide · RBW 30 Hz',
          'adf_wide_3hz': 'Previous ADF (0PLL) · RBW 3 Hz'}


def describe(trace):
    x, y = trace['offset_hz'], trace['relative_dbc']
    bands = []
    for lo, hi in BANDS_KHZ:
        # Require both sides to cover the whole band; avoid partial-band medians.
        if min(-x.min(), x.max()) < hi*1000:
            continue
        mask = (abs(x) >= lo*1000) & (abs(x) < hi*1000)
        native_db = float(np.median(y[mask]))
        bands.append(dict(low_khz=lo, high_khz=hi, display_points=int(mask.sum()),
                          median_native_dbc=native_db,
                          median_rbw_corrected_db=native_db-10*np.log10(trace['metadata']['rbw_hz'])))
    return dict(metadata=trace['metadata'], bands=bands,
                lines_5khz=strongest_lines(trace, 3000, 8500),
                lines_47khz=strongest_lines(trace, 43000, 54000))


def main():
    traces = {key: load_trace(name) for key, name in FILES.items()}
    assert all(t['metadata']['detector'] == 'Positive' for t in traces.values())
    narrow = [traces[key] for key in ('fpga_narrow', 'adf_narrow')]
    assert all(t['metadata']['rbw_hz'] == t['metadata']['vbw_hz'] == 1 for t in narrow)
    assert np.isclose(narrow[0]['metadata']['display_spacing_hz'],
                      narrow[1]['metadata']['display_spacing_hz'])
    summaries = {key: describe(t) for key, t in traces.items()}
    wide_differences = []
    for baseline in ('adf_wide_30hz', 'adf_wide_3hz', 'previous_fpga_wide'):
        for new in summaries['fpga_wide']['bands']:
            old = next((r for r in summaries[baseline]['bands']
                        if (r['low_khz'], r['high_khz']) == (new['low_khz'], new['high_khz'])), None)
            if old:
                wide_differences.append(dict(baseline=baseline, low_khz=new['low_khz'],
                    high_khz=new['high_khz'],
                    new_fpga_minus_baseline_db=new['median_rbw_corrected_db']-old['median_rbw_corrected_db']))

    plt.rcParams.update({'font.size': 10, 'axes.titlesize': 11})
    fig, axes = plt.subplots(2, 2, figsize=(13.2, 8.6), layout='constrained')
    for key in COLORS:
        t = traces[key]; x = t['offset_hz']/1000
        axes[0, 0].plot(x, t['relative_dbc'], color=COLORS[key], lw=1, label=LABELS[key])
        axes[0, 1].plot(x, t['density_proxy'], color=COLORS[key], lw=1, label=LABELS[key])
        # Five-point median reduces single-bin lines when locating the broad
        # shoulder. It is a visual guide, never used for the band statistics.
        smoothed = median_filter(t['density_proxy'], size=5, mode='nearest')
        axes[1, 0].plot(x, t['density_proxy'], color=COLORS[key], alpha=.22, lw=.7)
        axes[1, 0].plot(x, smoothed, color=COLORS[key], lw=1.4, label=LABELS[key])
    axes[0, 0].set(xlim=(-560, 560), ylim=(-65, 3),
                   title='Native line heights: different RBWs', ylabel='Displayed level relative to carrier (dBc)')
    axes[0, 1].set(xlim=(-560, 560), ylim=(-69, -25),
                   title='Approximate broadband comparison after RBW correction',
                   ylabel='Relative display level − 10 log₁₀(RBW/Hz) (dB)')
    axes[1, 0].set(xlim=(100, 450), ylim=(-65, -35),
                   title='Similar broad shoulder around 300–400 kHz',
                   ylabel='Relative display level − 10 log₁₀(RBW/Hz) (dB)')
    axes[1, 0].axvspan(300, 400, color='gray', alpha=.08)
    for ax in (axes[0, 0], axes[0, 1], axes[1, 0]):
        ax.set_xlabel('Offset from each displayed carrier (kHz)')
        ax.grid(alpha=.22); ax.legend(fontsize=8)
    comparison_bands = [(60, 100), (100, 200), (200, 300), (300, 400)]
    for index, key in enumerate(('adf_wide_30hz', 'adf_wide_3hz')):
        values = [next(r['new_fpga_minus_baseline_db'] for r in wide_differences
                       if r['baseline'] == key and (r['low_khz'], r['high_khz']) == band)
                  for band in comparison_bands]
        axes[1, 1].bar(np.arange(4)+(index-.5)*.36, values, width=.36,
                       color=COLORS[key], label=LABELS[key])
    axes[1, 1].axhline(0, color='black', lw=.8)
    axes[1, 1].set_xticks(np.arange(4), [f'{a}–{b}' for a, b in comparison_bands])
    axes[1, 1].set(xlabel='Absolute offset band (kHz)', ylabel='New FPGA − ADF band median (dB)',
                   title='Positive means FPGA has higher displayed sidebands')
    axes[1, 1].legend(fontsize=8); axes[1, 1].grid(axis='y', alpha=.22)
    fig.suptitle('New wide FPGA beat spectrum versus both previous wide ADF4108 records\n'
                 'Independent carrier alignment/normalization: FPGA 800 MHz, ADF 1 GHz', fontsize=13)
    fig.supxlabel('Nominal RBW correction applies approximately to broadband noise, not discrete tones. '
                  'Positive-peak buckets; incomplete-sweep warnings. No RMS phase integral inferred.', fontsize=9)
    for ext in ('png', 'pdf'):
        fig.savefig(OUT/f'new_fpga_wide_comparison.{ext}', dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), layout='constrained')
    for t, label, color in zip(narrow, ('New FPGA narrow', 'New ADF narrow'), ('#1769aa', '#c35b25')):
        for ax in axes:
            ax.plot(t['offset_hz']/1000, t['relative_dbc'], '.-', color=color,
                    lw=.9, ms=2.4, label=label)
    axes[0].set(xlim=(-55, 55), ylim=(-58, 3), title='Matched RBW, span, attenuation and display spacing')
    axes[1].set(xlim=(-11, 11), ylim=(-55, 3), title='±5 kHz lines: FPGA lower by 16.3–16.5 dB')
    axes[2].set(xlim=(40, 54), ylim=(-53, -17), title='+47 kHz family persists in both')
    for ax in axes:
        ax.set(xlabel='Offset from each displayed carrier (kHz)', ylabel='Displayed level relative to carrier (dBc)')
        ax.grid(alpha=.22); ax.legend(fontsize=8)
    fig.suptitle('New narrow beat spectra: 1 Hz RBW/VBW; 273 Hz display spacing\n'
                 '1–10 kHz median display level: FPGA −43.45 dBc, ADF −38.84 dBc', fontsize=13)
    fig.supxlabel('AM and PM are combined. Display statistics are not integrated RMS phase noise. '
                  'All source files carry an incomplete-sweep warning.', fontsize=9)
    for ext in ('png', 'pdf'):
        fig.savefig(OUT/f'new_fpga_narrow_comparison.{ext}', dpi=180)
    plt.close(fig)

    report = dict(traces=summaries, wide_band_differences=wide_differences,
        assumptions=['File names identify FPGA versus ADF feedback; current gains/filter settings are not supplied.',
                     'Each trace is normalized to its own displayed carrier peak.',
                     'Input attenuation is already calibrated into analyzer dBm; no extra attenuation correction.'],
        limitations=['RF power combines amplitude and phase noise.',
                     'Sparse positive-peak display buckets cannot be integrated as a phase PSD.',
                     'Nominal RBW correction omits filter ENBW and detector/sweep bias; do not apply it to resolved line powers.',
                     'Carrier levels, measurement times and carrier frequencies differ.',
                     'A broad spectral shoulder does not by itself measure crossover or phase margin.',
                     'All traces flag an incomplete sweep.'])
    (OUT/'new_fpga_spectra_comparison.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(wide_differences, indent=2))
    print('Wrote wide/narrow PNG/PDF comparisons and JSON provenance/statistics.')


if __name__ == '__main__':
    main()
