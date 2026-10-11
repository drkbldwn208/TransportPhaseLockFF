"""Phase, fractional-amplitude and cross spectra of saved baseband I/Q.

No small-phase approximation: phase-only envelope is z/|z|. The direct complex
spectra are normalized by mean amplitude, not the often-small coherent carrier.
AM is |z|/mean(|z|)-1. CSD convention is conj(AM_fft)*phase_fft; positive cross
phase means phase fluctuations lead AM. I/Q averaging precedes phase extraction.
"""
from pathlib import Path
import hashlib
import json
import os

os.environ.setdefault('MPLCONFIGDIR','/tmp/laser_iq_matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

ROOT=Path(__file__).resolve().parent
PSD_LENGTH=65536
CROSS_LENGTH=16384
COLORS={'fast':'#1769aa','slow':'#c45324'}


def spectra(x, fs_hz, length, y=None):
    kwargs=dict(fs=fs_hz,window='hann',nperseg=length,noverlap=length//2,
                detrend='constant',scaling='density')
    return signal.welch(x,**kwargs) if y is None else signal.csd(x,y,**kwargs)


def fold_complex_psd(z, fs_hz, length):
    _,p=signal.welch(z,fs=fs_hz,window='hann',nperseg=length,noverlap=length//2,
                     detrend='constant',scaling='density',return_onesided=False)
    folded=p[:length//2+1].copy()
    folded[1:-1]+=p[:length//2:-1]
    return np.fft.rfftfreq(length,1/fs_hz),folded


def check_normalization(x, fs_hz, length, psd):
    """Parseval check against the same detrended Hann-windowed records."""
    w=signal.windows.hann(length,sym=False)
    segments=np.lib.stride_tricks.sliding_window_view(x,length)[::length//2]
    expected=np.mean(np.sum(abs((segments-segments.mean(axis=1,keepdims=True))*w)**2,axis=1)/sum(w*w))
    measured=np.sum(psd)*fs_hz/length
    assert np.isclose(expected,measured,rtol=1e-10),(expected,measured)


def analyze(kind):
    path=ROOT/f'laser_iq_{kind}.npz'
    with np.load(path) as data:
        z=np.asarray(data['i_adc_counts'],float)+1j*np.asarray(data['q_adc_counts'],float)
        fs_hz=float(data['sample_rate_hz']); decimation=int(data['decimation_log2'])
    assert np.all(np.isfinite(z)) and np.min(abs(z))>0
    time_s=np.arange(len(z))/fs_hz
    amplitude=abs(z); mean_amplitude=amplitude.mean()
    am=amplitude/mean_amplitude-1
    phase=np.unwrap(np.angle(z))
    slope,offset=np.polyfit(time_s,phase,1)
    phase_residual=phase-(slope*time_s+offset)
    f_hz,s_phase=spectra(phase_residual,fs_hz,PSD_LENGTH)
    _,s_am=spectra(am,fs_hz,PSD_LENGTH)
    _,s_envelope=fold_complex_psd(z/mean_amplitude,fs_hz,PSD_LENGTH)
    _,s_phase_only=fold_complex_psd(z/amplitude,fs_hz,PSD_LENGTH)
    check_normalization(phase_residual,fs_hz,PSD_LENGTH,s_phase)
    check_normalization(am,fs_hz,PSD_LENGTH,s_am)
    check_normalization(z/mean_amplitude,fs_hz,PSD_LENGTH,s_envelope)
    cross_f_hz,cross=spectra(am,fs_hz,CROSS_LENGTH,phase_residual)
    _,cross_am=spectra(am,fs_hz,CROSS_LENGTH)
    _,cross_phase=spectra(phase_residual,fs_hz,CROSS_LENGTH)
    coherence=abs(cross)**2/(cross_am*cross_phase)
    assert np.max(coherence)<=1+1e-10
    count=1+(len(z)-CROSS_LENGTH)//(CROSS_LENGTH//2)
    w=signal.windows.hann(CROSS_LENGTH,sym=False)
    rho=np.dot(w[:CROSS_LENGTH//2],w[CROSS_LENGTH//2:])/np.dot(w,w)
    effective=count/(1+2*(1-1/count)*rho**2)
    threshold=1-0.05**(1/(effective-1))
    summary=dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),samples=len(z),
                 fs_hz=fs_hz,duration_s=len(z)/fs_hz,decimation_log2=decimation,
                 amplitude_mean_adc_counts=float(mean_amplitude),
                 amplitude_fractional_rms=float(am.std()),
                 amplitude_percentiles_adc_counts=np.percentile(amplitude,[0,1,50,99,100]).tolist(),
                 detrended_phase_rms_rad=float(phase_residual.std()),
                 phase_span_turns=float(np.ptp(phase)/(2*np.pi)),
                 fitted_phase_slope_hz=float(slope/(2*np.pi)),
                 coherent_mean_power_fraction=float(abs(z.mean())**2/np.mean(abs(z)**2)),
                 fraction_phase_steps_over_pi_over_2=float(np.mean(abs(np.diff(phase))>np.pi/2)),
                 psd_bin_spacing_hz=fs_hz/PSD_LENGTH,psd_hann_enbw_hz=1.5*fs_hz/PSD_LENGTH,
                 psd_segments=1+(len(z)-PSD_LENGTH)//(PSD_LENGTH//2),
                 cross_bin_spacing_hz=fs_hz/CROSS_LENGTH,cross_segments=count,
                 approximate_per_bin_coherence_95_threshold=threshold)
    df=fs_hz/PSD_LENGTH
    summary['band_phase_rms_rad']={}
    for lo,hi in [(10,100),(100,1000),(1000,10000),(1e4,1e5),(1e5,1e6),(170e3,180e3)]:
        mask=(f_hz>=lo)&(f_hz<=hi)
        if mask.sum()>1:
            summary['band_phase_rms_rad'][f'{lo:g}-{hi:g} Hz']=float(np.sqrt(s_phase[mask].sum()*df))
    peaks,_=signal.find_peaks(s_phase)
    top=peaks[np.argsort(s_phase[peaks])[-8:]][::-1]
    summary['largest_phase_psd_peaks']=[dict(frequency_hz=float(f_hz[k]),psd_rad2_per_hz=float(s_phase[k])) for k in top]
    for frequency in (500,20000,175000):
        if frequency<fs_hz/2:
            k=np.argmin(abs(cross_f_hz-frequency))
            summary[f'cross_near_{frequency}_Hz']=dict(frequency_hz=float(cross_f_hz[k]),
                coherence=float(coherence[k]),phase_deg=float(np.angle(cross[k],deg=True)))
    np.savetxt(ROOT/f'laser_iq_{kind}_psd.csv',np.column_stack((f_hz,s_phase,s_am,s_envelope,s_phase_only)),
               delimiter=',',header='frequency_Hz,phase_rad2_per_Hz,fractional_amplitude_1_per_Hz,full_envelope_folded_1_per_Hz,phase_only_envelope_folded_1_per_Hz',comments='')
    np.savetxt(ROOT/f'laser_iq_{kind}_cross_psd.csv',
               np.column_stack((cross_f_hz,cross.real,cross.imag,abs(cross),np.angle(cross,deg=True),coherence,cross_am,cross_phase)),
               delimiter=',',header='frequency_Hz,cross_real_rad_per_Hz,cross_imag_rad_per_Hz,cross_abs_rad_per_Hz,cross_phase_deg,coherence,AM_1_per_Hz,phase_rad2_per_Hz',comments='')
    return dict(kind=kind,z=z,am=am,phase=phase_residual,time_s=time_s,fs=fs_hz,f=f_hz,
                pp=s_phase,aa=s_am,full=s_envelope,phase_only=s_phase_only,
                cf=cross_f_hz,cross=cross,coherence=coherence,threshold=threshold,summary=summary)


def style(ax):
    ax.grid(True,which='both',alpha=0.22)
    ax.set_xlabel('Fourier frequency / |DDS offset| (Hz)')


def figures(records):
    plt.rcParams.update({'font.size':10,'axes.titlesize':11,'figure.dpi':120})
    fig,axes=plt.subplots(3,2,figsize=(13,11),layout='constrained')
    for col,r in enumerate(records):
        f=r['f'][1:]; color=COLORS[r['kind']]
        axes[0,col].semilogx(f,10*np.log10(r['full'][1:]),label='Full I/Q: AM + phase',lw=1,color=color)
        axes[0,col].semilogx(f,10*np.log10(r['phase_only'][1:]),label='Amplitude normalized: phase only',lw=1,color='#30343b',alpha=.8)
        axes[0,col].set_ylabel('Normalized envelope PSD (dB/Hz)')
        axes[0,col].legend(fontsize=9)
        axes[0,col].set_title(f"{r['kind'].capitalize()}: {r['fs']/1000:g} kS/s, {len(r['z'])/r['fs']:.4g} s\nHann bin spacing {r['fs']/PSD_LENGTH:.4g} Hz; 7 averages")
        axes[1,col].loglog(f,r['pp'][1:],color=color,lw=1)
        axes[1,col].set_ylabel('Phase PSD (rad²/Hz)')
        axes[2,col].loglog(f,r['aa'][1:],color=color,lw=1)
        axes[2,col].set_ylabel('Fractional-amplitude PSD (1/Hz)')
        if r['kind']=='fast':
            axes[1,col].axvline(175312.5,color='0.3',ls='--',lw=.8)
            axes[1,col].annotate('~175 kHz feature',xy=(175312.5,.0002156),xytext=(4000,.002),
                                 arrowprops={'arrowstyle':'->'},fontsize=9)
        else:
            axes[1,col].text(.03,.05,'Apparent slow phase: near-zero vectors and\npre-arctan averaging limit interpretation.',
                             transform=axes[1,col].transAxes,fontsize=9,color='#913619',bbox=dict(facecolor='white',alpha=.9,edgecolor='none'))
        for ax in axes[:,col]: style(ax); ax.set_xlim(f[0],f[-1])
    fig.suptitle('Measured baseband spectra — direct full envelope and amplitude-normalized phase-only envelope\n'
                 'Envelope power normalized to mean amplitude²; ±offset spectra summed (not conventional small-signal dBc/Hz).',fontsize=12)
    fig.savefig(ROOT/'laser_iq_psd_comparison.png',dpi=180)
    fig.savefig(ROOT/'laser_iq_psd_comparison.pdf')
    plt.close(fig)

    fig,axes=plt.subplots(3,2,figsize=(13,10),layout='constrained')
    for col,r in enumerate(records):
        f=r['cf'][1:]; c=r['cross'][1:]; coh=r['coherence'][1:]; color=COLORS[r['kind']]
        axes[0,col].loglog(f,abs(c),lw=.8,color=color)
        axes[0,col].set_ylabel('|AM–phase cross-PSD| (rad/Hz)')
        axes[0,col].set_title(f"{r['kind'].capitalize()}: {r['fs']/CROSS_LENGTH:.4g} Hz bins, 31 averages")
        good=coh>r['threshold']
        axes[1,col].semilogx(f,np.angle(c,deg=True),'.',ms=1,color='0.7',alpha=.4)
        axes[1,col].semilogx(f[good],np.angle(c[good],deg=True),'.',ms=2,color=color,alpha=.7)
        axes[1,col].set_ylim(-185,185); axes[1,col].set_ylabel('Cross phase (deg)')
        axes[2,col].semilogx(f,coh,color=color,lw=.6)
        axes[2,col].axhline(r['threshold'],color='0.25',ls='--',label='Approx. per-bin 95% null threshold')
        axes[2,col].set_ylabel('Magnitude-squared coherence'); axes[2,col].set_ylim(0,1)
        axes[2,col].legend(fontsize=8,loc='upper right')
        for ax in axes[:,col]: style(ax); ax.set_xlim(f[0],f[-1])
    fig.suptitle('Amplitude–phase correlation: C = ⟨AM* × phase⟩; positive cross phase means phase leads AM\n'
                 'Gray phase points have low coherence. Threshold is approximate, per-bin and not corrected for multiple comparisons.',fontsize=12)
    fig.savefig(ROOT/'laser_iq_cross_psd.png',dpi=180)
    fig.savefig(ROOT/'laser_iq_cross_psd.pdf')
    plt.close(fig)

    fig,axes=plt.subplots(2,2,figsize=(13,7),layout='constrained')
    for col,r in enumerate(records):
        stride=max(1,len(r['z'])//15000)
        axes[0,col].plot(r['time_s'][::stride],r['phase'][::stride]/(2*np.pi),lw=.5,color=COLORS[r['kind']])
        axes[0,col].set_title(r['kind'].capitalize()); axes[0,col].set_ylabel('Detrended phase (turns)')
        axes[1,col].plot(r['time_s'][::stride],1+r['am'][::stride],lw=.5,color=COLORS[r['kind']])
        axes[1,col].set_ylabel('Amplitude / mean amplitude')
        for ax in axes[:,col]: ax.set_xlabel('Time (s)'); ax.grid(alpha=.25)
    fig.suptitle('Time-domain checks: one global phase line removed; displayed points thinned only for plotting')
    fig.savefig(ROOT/'laser_iq_time_series.png',dpi=180); plt.close(fig)


def averaging_check(fast,slow):
    ratio=round(fast['fs']/slow['fs'])
    assert ratio==256
    z=fast['z']; count=len(z)//ratio*ratio
    averaged=z[:count].reshape(-1,ratio).mean(axis=1)
    phase_only=(z/abs(z))[:count].reshape(-1,ratio).mean(axis=1)
    series=[('Fast original',abs(z)),('Fast re-averaged to 60 kS/s',abs(averaged)),
            ('Fast phase-only, then averaged',abs(phase_only)),('Slow measured',abs(slow['z']))]
    fig,ax=plt.subplots(figsize=(10,5),layout='constrained')
    summary={}
    for label,amplitude in series:
        frac=amplitude/amplitude.mean()-1
        rms=float(np.std(frac)); summary[label]=rms
        ax.hist(frac,bins=np.linspace(-1,.6,161),density=True,histtype='step',lw=1.5,label=f'{label}: {100*rms:.2f}% RMS')
    ax.set_yscale('log'); ax.set_xlabel('Fractional amplitude deviation'); ax.set_ylabel('Probability density')
    ax.legend(fontsize=9); ax.grid(alpha=.2)
    ax.set_title('Averaging rotating I/Q produces apparent AM, even when its original amplitude is fixed')
    fig.savefig(ROOT/'laser_iq_averaging_check.png',dpi=180); plt.close(fig)
    return summary


def synthetic_check():
    fs=65536.; t=np.arange(131072)/fs
    am=.05*np.sin(2*np.pi*1024*t)
    phase=.1*np.sin(2*np.pi*1024*t+.4)
    f,c=spectra(am,fs,16384,phase)
    _,p=spectra(phase,fs,16384)
    assert np.isclose(sum(p)*(f[1]-f[0]),.1**2/2,rtol=1e-8)
    assert abs(np.angle(c[np.argmax(abs(c))])-.4)<1e-8


if __name__=='__main__':
    synthetic_check()
    records=[analyze('fast'),analyze('slow')]
    figures(records)
    summary=dict(captures=[r['summary'] for r in records],averaging_test=averaging_check(*records),
                 acquisition_conditions='User confirmed identical loop settings; only acquisition duration/rate changed.',
                 conventions={'phase':'unwrap(angle(I+jQ)), one global best-fit line removed; Welch removes each segment mean',
                              'amplitude':'abs(I+jQ)/mean(abs(I+jQ))-1',
                              'envelope':'direct complex PSD of z/mean(abs(z)) and z/abs(z), positive+negative offsets summed',
                              'cross':'conj(AM_fft)*phase_fft; rad/Hz; positive phase means phase leads AM'},
                 cautions=['Slow I/Q averaging can create apparent AM and phase ambiguity from rapid phase motion.',
                           'Slow phase span/slope are properties of averaged vectors, not a proven optical slip count or detuning.',
                           'Spectra are normalized to mean amplitude, not coherent-carrier power; no small-phase dBc/Hz approximation.',
                           'Record-to-record differences need identical loop settings and stationarity to be interpreted physically.',
                           'Coherence indicates correlation, not causal AM-to-PM conversion.'])
    (ROOT/'laser_iq_spectral_analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
