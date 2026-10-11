"""Compare recorded analog-lock and FPGA-lock I/Q with matched Welch windows.

The old 960 kS/s receiver and current 15.36 MS/s receiver have different input
filters. No deconvolution or coherent-carrier dBc calibration is implied.
The old record is divided into 17.067 ms pieces, matching the new fast record,
to show physical variability rather than mistake a long average for certainty.
"""
from pathlib import Path
import hashlib
import json
import os

os.environ.setdefault('MPLCONFIGDIR', '/tmp/laser_iq_matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import h5py
import numpy as np
from scipy import optimize, signal

ROOT = Path(__file__).resolve().parent
BASELINE = Path('/home/levlabcukomen/Desktop/DyAnalysis/10-05-26/PSD_data_light_on (1)')


def record_spectra(z, fs_hz, record_length, segment_length):
    count = len(z)//record_length
    blocks = z[:count*record_length].reshape(count, record_length)
    phase = signal.detrend(np.unwrap(np.angle(blocks), axis=-1), axis=-1)
    amplitude = abs(blocks)
    mean_amplitude = amplitude.mean(axis=-1, keepdims=True)
    am = amplitude/mean_amplitude-1
    kw = dict(fs=fs_hz, window='hann', nperseg=segment_length,
              noverlap=segment_length//2, detrend='constant', scaling='density', axis=-1)
    f, pp = signal.welch(phase, **kw)
    _, aa = signal.welch(am, **kw)
    _, ap = signal.csd(am, phase, **kw)
    envelopes = []
    for x in (blocks/mean_amplitude, blocks/amplitude):
        _, p = signal.welch(x, return_onesided=False, **kw)
        folded = p[:, :segment_length//2+1].copy()
        folded[:, 1:-1] += p[:, :segment_length//2:-1]
        envelopes.append(folded)
    c = ap.mean(axis=0)
    return dict(f=f, phase=pp, am=aa, cross=c,
                coherence=abs(c)**2/(aa.mean(axis=0)*pp.mean(axis=0)),
                full=envelopes[0], phase_only=envelopes[1], blocks=count)


def line_detail(z, fs_hz):
    phase = signal.detrend(np.unwrap(np.angle(z)))
    f, p = signal.welch(phase, fs=fs_hz, nperseg=len(z), window='hann')
    indices = np.flatnonzero((f>170000)&(f<180000))
    peak = indices[np.argmax(p[indices])]
    width, _, left, right = signal.peak_widths(p, [peak], rel_height=.5)
    time_s = np.arange(len(z))/fs_hz
    w = signal.windows.hann(len(z), sym=False)
    estimate = optimize.minimize_scalar(
        lambda frequency: -abs(np.sum(w*phase*np.exp(-2j*np.pi*frequency*time_s)))**2,
        bounds=(f[peak]-f[1], f[peak]+f[1]), method='bounded')
    tone_hz = estimate.x
    # Compare width with the exact finite-record Hann response to a pure sine.
    _, ideal = signal.welch(np.sin(2*np.pi*tone_hz*time_s), fs=fs_hz,
                            nperseg=len(z), window='hann')
    ideal *= p[peak]/ideal.max()
    summary = dict(peak_frequency_hz=float(tone_hz), bin_spacing_hz=float(f[1]),
                   apparent_fwhm_hz=float(width[0]*f[1]),
                   fwhm_left_hz=float(left[0]*f[1]), fwhm_right_hz=float(right[0]*f[1]),
                   note='Single 17 ms record; apparent width is window/drift limited, not an intrinsic linewidth or crossover measurement.')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout='constrained')
    axes[0].semilogy(f, p, lw=1)
    axes[0].set_xlim(150000, 200000)
    axes[0].set_ylim(1e-8, .002)
    axes[0].set_title('175 kHz phase feature — full-record periodogram')
    axes[1].plot(f, 10*np.log10(p), '.-', label='Measured')
    axes[1].plot(f, 10*np.log10(np.maximum(ideal, 1e-30)), '--', label='Pure sine, same Hann window')
    axes[1].set_xlim(tone_hz-700, tone_hz+700)
    axes[1].set_ylim(-75, -25)
    axes[1].set_title(f'Observed FWHM ≈ {width[0]*f[1]:.0f} Hz; bins {f[1]:.1f} Hz')
    axes[1].legend(fontsize=9)
    axes[0].set_ylabel('Phase PSD (rad²/Hz)')
    axes[1].set_ylabel('Phase PSD (dB re 1 rad²/Hz)')
    for ax in axes:
        ax.set_xlabel('Fourier frequency (Hz)'); ax.grid(alpha=.25)
    fig.savefig(ROOT/'laser_iq_175khz_detail.png', dpi=180)
    plt.close(fig)
    return summary


def main():
    with h5py.File(BASELINE, 'r') as h:
        old_fs = float(h.attrs['sample_rate_hz'])
        old_z = h['I_channel'][:].astype(float)+1j*h['Q_channel'][:].astype(float)
    # Exclude startup consistently with the earlier receiver analyses.
    old_z = old_z[round(.2*old_fs):]
    with np.load(ROOT/'laser_iq_fast.npz') as h:
        new_fs = float(h['sample_rate_hz'])
        new_z = h['i_adc_counts']+1j*h['q_adc_counts']
    assert new_fs/old_fs == 16
    assert np.min(abs(old_z))>0 and np.min(abs(new_z))>0
    old = record_spectra(old_z, old_fs, 16384, 4096)
    new = record_spectra(new_z, new_fs, 262144, 65536)
    # A sensitivity check, not a reconstruction of the old acquisition filter.
    matched = record_spectra(signal.resample_poly(new_z, 1, 16), old_fs, 16384, 4096)
    assert np.array_equal(old['f'], new['f'][:len(old['f'])])
    f = old['f']
    bands = []
    for lo, hi in ((234.375, 1000), (1000, 10000), (10000, 100000),
                   (100000, 200000), (170000, 180000)):
        old_mask = (f>=lo)&(f<hi)
        new_mask = (new['f']>=lo)&(new['f']<hi)
        old_power = old['phase'][:, old_mask].sum(axis=1)*f[1]
        new_power = float(new['phase'][0, new_mask].sum()*f[1])
        matched_power = float(matched['phase'][0, old_mask].sum()*f[1])
        bands.append(dict(low_hz=lo, high_hz=hi,
            old_rms_rad=float(np.sqrt(old_power.mean())), new_rms_rad=float(np.sqrt(new_power)),
            old_17ms_rms_percentiles_rad=np.sqrt(np.percentile(old_power, [10,50,90])).tolist(),
            new_minus_old_db=float(10*np.log10(new_power/old_power.mean())),
            resampled_new_rms_rad=float(np.sqrt(matched_power))))
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), layout='constrained')
    for ax, key, ylabel in ((axes[0,0], 'phase', 'Phase PSD (rad²/Hz)'),
                            (axes[0,1], 'am', 'Fractional-amplitude PSD (1/Hz)')):
        p = old[key]
        lo, hi = np.percentile(p, [10,90], axis=0)
        ax.fill_between(f[1:], lo[1:], hi[1:], color='0.7', alpha=.4,
                        label='Old: 10–90% of 17 ms records')
        ax.loglog(f[1:], p.mean(axis=0)[1:], color='0.3', label='Old analog lock: mean')
        ax.loglog(new['f'][1:], new[key][0,1:], color='#1769aa', label='Current FPGA lock')
        ax.loglog(f[1:], matched[key][0,1:], '--', color='#c45324', lw=.8,
                  label='Current resampled to old rate')
        ax.set_ylabel(ylabel)
    ax = axes[1,0]
    for data, color, name in ((old, '0.3', 'Old'), (new, '#1769aa', 'Current')):
        for key, ls, label in (('full','-','full I/Q'), ('phase_only','--','phase only')):
            ax.semilogx(data['f'][1:], 10*np.log10(data[key].mean(axis=0)[1:]),
                        color=color, ls=ls, lw=1, label=f'{name}: {label}')
    ax.set_ylabel('Folded envelope PSD (dB/Hz re mean amplitude²)')
    ax.set_ylim(-90, -25)
    ax = axes[1,1]
    for data, color, name in ((old, '0.3', 'Old'), (new, '#1769aa', 'Current')):
        ax.loglog(data['f'][1:], abs(data['cross'][1:]), color=color, lw=.8, label=name)
    ax.set_ylabel('|AM–phase cross-PSD| (rad/Hz)')
    ax.set_ylim(1e-10, 1e-5)
    axes[0,0].set_ylim(1e-8, .03)
    for ax in axes.flat:
        ax.set_xlim(f[1], 200000); ax.grid(True, which='both', alpha=.2)
        ax.set_xlabel('Fourier frequency (Hz)'); ax.legend(fontsize=8)
        ax.axvspan(100000, 200000, color='#f1bd57', alpha=.1)
    fig.suptitle('Analog-lock baseline vs FPGA lock: identical 4.267 ms Hann windows, 234.375 Hz bins\n'
                 'Old: 222 × 17.067 ms records; current: one. Receiver filters differ; shaded high band needs caution.', fontsize=11)
    fig.savefig(ROOT/'laser_lock_psd_comparison.png', dpi=180)
    fig.savefig(ROOT/'laser_lock_psd_comparison.pdf')
    plt.close(fig)
    n = len(f)
    np.savetxt(ROOT/'laser_lock_psd_comparison.csv', np.column_stack((f,
        old['phase'].mean(axis=0), new['phase'][0,:n], matched['phase'][0],
        old['am'].mean(axis=0), new['am'][0,:n], old['cross'].real, old['cross'].imag,
        new['cross'][:n].real, new['cross'][:n].imag)), delimiter=',', comments='',
        header='frequency_Hz,old_phase_rad2_per_Hz,new_phase_rad2_per_Hz,resampled_new_phase_rad2_per_Hz,old_fractional_AM_per_Hz,new_fractional_AM_per_Hz,old_cross_real_rad_per_Hz,old_cross_imag_rad_per_Hz,new_cross_real_rad_per_Hz,new_cross_imag_rad_per_Hz')
    summary = dict(baseline=str(BASELINE), baseline_sha256=hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
        baseline_confirmed_by_user=True, old_sample_rate_hz=old_fs, new_sample_rate_hz=new_fs,
        old_start_trim_s=.2, comparison_record_duration_s=16384/old_fs,
        old_comparison_records=old['blocks'], bands=bands,
        line_detail=line_detail(new_z, new_fs),
        limitations=['Different receiver filters, carrier frequencies and possibly analog settings; comparison is of measured records, not isolated FPGA hardware noise.',
                     'Old record contains occasional near-zero vectors; unwrap-derived low-frequency noise requires caution.',
                     'Current slow capture is omitted from quantitative improvement ratios because pre-arctan averaging creates phase ambiguity.',
                     'Only one new 17 ms record; no established long-term improvement or optical linewidth.'])
    (ROOT/'laser_lock_psd_comparison.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
