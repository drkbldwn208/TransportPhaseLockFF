"""Compare matched 3 Hz RBW RF display traces, preserving their native buckets.

These positive-peak records are not uniformly sampled phase-noise PSDs. Compare
carrier-relative levels and resolved features; do not integrate them as S_phi.
The 1 GHz ADF and 800 MHz FPGA carriers are independently aligned and normalized.
"""
from pathlib import Path
import json
import numpy as np
import matplotlib.pyplot as plt
from compare_adf_fpga_lock import load_trace, strongest_lines

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '10-13SpectrumAnalyzer'


def main():
    names = ['0PLL', '0W', '0WNS']
    labels = ['ADF4108: File_0PLL', 'FPGA /160: W', 'FPGA /160: WNS']
    colors = ['#c45722', '#1769aa', '#27806b']
    traces = [load_trace(f'10-13SpectrumAnalyzer/File_{name}.csv') for name in names]
    assert all(t['metadata']['rbw_hz'] == t['metadata']['vbw_hz'] == 3 for t in traces)
    assert all(t['metadata']['detector'] == 'Positive' for t in traces)
    bands_khz = [(1, 10), (10, 30), (30, 60), (60, 100), (100, 200), (200, 300), (300, 400)]
    results = []
    for label, trace in zip(labels, traces):
        x, y = trace['offset_hz'], trace['relative_dbc']
        bands = []
        for lo, hi in bands_khz:
            selected = (abs(x) >= lo*1000) & (abs(x) < hi*1000)
            bands.append(dict(low_khz=lo, high_khz=hi, points=int(selected.sum()),
                              median_display_dbc=float(np.median(y[selected]))))
        results.append(dict(label=label, metadata=trace['metadata'], bands=bands,
                            close_features=strongest_lines(trace, 3000, 8500),
                            features_50khz=strongest_lines(trace, 40000, 60000)))
    differences = []
    for index, (lo, hi) in enumerate(bands_khz):
        adf = results[0]['bands'][index]['median_display_dbc']
        differences.append(dict(low_khz=lo, high_khz=hi,
                                fpga_W_minus_adf_db=results[1]['bands'][index]['median_display_dbc']-adf,
                                fpga_WNS_minus_adf_db=results[2]['bands'][index]['median_display_dbc']-adf))

    plt.rcParams.update({'font.size': 10, 'axes.titlesize': 11})
    fig, axes = plt.subplots(2, 2, figsize=(12.6, 8), layout='constrained')
    for trace, label, color in zip(traces, labels, colors):
        x, y = trace['offset_hz']/1000, trace['relative_dbc']
        for ax in (axes[0, 0], axes[0, 1], axes[1, 0]):
            ax.plot(x, y, '.-', color=color, label=label, lw=1, ms=3)
    axes[0, 0].set(xlim=(-405, 405), ylim=(-63, -17), title='Wide span: FPGA has the lower 300–400 kHz shoulder')
    axes[0, 1].set(xlim=(-13, 13), ylim=(-47, 3), title='Close-in: only 6–8 noncarrier points in 1–10 kHz')
    axes[1, 0].set(xlim=(-65, 65), ylim=(-49, -19), title='The ±50 kHz features have similar peak levels')
    for ax in (axes[0, 0], axes[0, 1], axes[1, 0]):
        ax.set(xlabel='Offset from displayed carrier peak (kHz)', ylabel='Carrier-relative displayed power (dBc)')
        ax.grid(alpha=.25)
    axes[0, 0].legend(fontsize=9, loc='lower center')
    labels_band = [f'{lo}–{hi}' for lo, hi in bands_khz]
    positions = np.arange(len(bands_khz))
    for index, field in enumerate(('fpga_W_minus_adf_db', 'fpga_WNS_minus_adf_db')):
        axes[1, 1].bar(positions + (index-.5)*.35, [r[field] for r in differences], width=.35,
                       color=colors[index+1], label=labels[index+1])
    axes[1, 1].axhline(0, color='k', lw=.8)
    axes[1, 1].set_xticks(positions, labels_band, rotation=30)
    axes[1, 1].set(ylabel='FPGA − ADF median displayed level (dB)', xlabel='Absolute offset band (kHz)',
                    title='Positive: ADF lower; negative: FPGA lower')
    axes[1, 1].grid(axis='y', alpha=.25)
    axes[1, 1].legend(fontsize=9)
    fig.suptitle('ADF4108 versus FPGA /160 with the same analog filter and gain settings\n'
                 'All shown traces: 3 Hz RBW/VBW, positive-peak detector; independently normalized carriers', fontsize=12)
    fig.supxlabel('Display spacing: ADF 2.04 kHz, FPGA 2.54 kHz. Band medians are display statistics, not integrated phase noise.\n'
                  'All files carry an incomplete-sweep warning; amplitude and phase noise are not separated.', fontsize=9)
    for suffix in ('png', 'pdf'):
        fig.savefig(OUT/f'adf_vs_fpga_160.{suffix}', dpi=180)
    plt.close(fig)
    summary = dict(traces=results, median_differences=differences,
                   user_conditions='Identical analog filters/gains; FPGA divide by 160; detector voltage slopes approximate.',
                   limitations=['Display buckets are wider than the 3 Hz RBW and have unequal spacing.',
                                'Positive detector, one average, incomplete-sweep flags.',
                                'No reliable integrated 1–10 kHz RMS phase noise from these files.',
                                'RF power spectra combine AM and PM; carrier frequencies differ.',
                                '50 kHz peak levels do not establish loop crossover or stability margin.'])
    (OUT/'adf_vs_fpga_160.json').write_text(json.dumps(summary, indent=2)+'\n')
    for result in results:
        print(result['label'], result['metadata']['carrier_display_power_dbm'], 'dBm carrier')
        print('Close features:', result['close_features'])
        print('50 kHz features:', result['features_50khz'])
    print('Band differences:', json.dumps(differences, indent=2))


if __name__ == '__main__':
    main()
