"""DC-command output noise and single-input D2S transfer response, 13 October.

Scope RMS values describe saved samples, not an anti-aliased low-frequency
noise integral. Analyzer data are positive-peak display buckets in 1 Hz RBW.
FRA column 1 is log10(frequency / Hz), not frequency in Hz.
"""
import csv
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/tmp/dc_10_13_matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import welch, find_peaks

ROOT = Path(__file__).resolve().parent


def scope_trace(path):
    rows = list(csv.reader(path.open()))
    metadata = {r[0]: r[1] for r in rows if r[0]}
    time_s, voltage_V = np.array([[float(r[3]), float(r[4])] for r in rows]).T
    dt_s = float(np.median(np.diff(time_s)))
    np.testing.assert_allclose(np.diff(time_s), dt_s, rtol=1e-6)
    assert metadata['Source'] == 'CH2' and len(time_s) == 2500
    stats = dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        metadata=metadata, sample_rate_hz=1/dt_s, duration_s=len(time_s)*dt_s,
        mean_V=float(voltage_V.mean()), fluctuation_rms_V=float(voltage_V.std()),
        peak_to_peak_V=float(np.ptp(voltage_V)),
        percentiles_1_99_V=np.quantile(voltage_V,[.01,.99]).tolist())
    return time_s-time_s[0], voltage_V, stats


def main():
    traces = [scope_trace(ROOT/'10-13Scope'/f'TEK000{k}.CSV') for k in [5,6,7]]
    sa_path = ROOT/'10-13SpectrumAnalyzer/File_0DC.csv'
    lines = sa_path.read_text().splitlines()
    frequency_hz, power_dbm = np.array([[float(s) for s in line.split(',')[:2]]
        for line in lines[lines.index('BEGIN')+1:lines.index('END')]]).T
    assert np.all(np.diff(frequency_hz)>0) and 'ResolutionBW 1' in sa_path.read_text()
    bands = []
    for low, high in [(5000,10000),(10000,30000),(45000,55000),(60000,100000),(100000,200000)]:
        selected = (frequency_hz>=low)&(frequency_hz<=high)
        median_dbm = float(np.median(power_dbm[selected]))
        bands.append(dict(low_hz=low,high_hz=high,median_display_dbm=median_dbm,
            voltage_asd_proxy_V_per_sqrtHz=float(np.sqrt(50*1e-3*10**(median_dbm/10)))))
    peaks,_ = find_peaks(power_dbm,prominence=5)
    sa = dict(file=str(sa_path.relative_to(ROOT)),sha256=hashlib.sha256(sa_path.read_bytes()).hexdigest(),
        rbw_hz=1,display_spacing_hz=500,detector='Positive peak',bands=bands,
        zero_frequency_display_dbm=float(power_dbm[0]),
        spurs=[dict(frequency_hz=float(frequency_hz[i]),power_dbm=float(power_dbm[i])) for i in peaks],
        caveat='No terminated-input baseline. Positive-peak buckets are not a calibrated noise PSD. '
               'DC bin and sub-5-kHz data excluded from physical interpretation.')
    plt.rcParams.update({'font.size':10,'axes.titlesize':11})
    fig,axes=plt.subplots(3,2,figsize=(13,10),layout='constrained')
    for (t,v,stats),ax,time_scale,time_unit in zip(traces,
            [axes[0,0],axes[1,0],axes[1,1]],[1e6,1,1],['µs','s','s']):
        ax.plot(t*time_scale,(v-v.mean())*1e3,lw=.6,color='#1769aa')
        ax.set(xlabel=f'Elapsed time ({time_unit})',ylabel='Voltage − record mean (mV)',
            ylim=(-2,2),title=f"{stats['file']} · {stats['sample_rate_hz']:g} samples/s · "
            f"RMS {stats['fluctuation_rms_V']*1e3:.3f} mV")
        ax.text(.02,.03,f"Mean = {stats['mean_V']*1e3:.3f} mV",transform=ax.transAxes,fontsize=9)
    t,v,stats=traces[0]
    f,psd=welch(v,stats['sample_rate_hz'],nperseg=1024,window='hann',detrend='constant')
    axes[0,1].loglog(f[1:]/1e3,np.sqrt(psd[1:])*1e9,color='#1769aa')
    axes[0,1].axvspan(45,55,color='orange',alpha=.18,label='45–55 kHz')
    axes[0,1].set(xlabel='Frequency in saved samples (kHz)',ylabel='Apparent ASD (nV/√Hz)',
                  title='Fast record: analog noise above 5 MHz can alias')
    axes[0,1].legend(fontsize=9)
    valid=frequency_hz>0
    for ax in axes[2]:
        ax.plot(frequency_hz[valid]/1e3,power_dbm[valid],color='#27806b',lw=1)
        ax.axvspan(45,55,color='orange',alpha=.12)
        ax.set(xlabel='Frequency (kHz)',ylabel='Displayed power (dBm in 1 Hz RBW)',ylim=(-125,-90))
    axes[2,0].set(xscale='log',xlim=(.5,200),title='DC-output spectrum: strong features near 8 and 35 kHz')
    axes[2,0].axvspan(.5,5,color='gray',alpha=.2,label='Below usable frequency range')
    axes[2,0].legend(fontsize=8,loc='lower left')
    axes[2,1].set(xlim=(20,80),title='No resolved 50 kHz feature in the DC-output record')
    for ax in axes.flat: ax.grid(alpha=.2,which='both')
    fig.suptitle('Constant DAC code 100 · D2S output · controllers connected\n'
        'No BLP; scope DC-coupled, bandwidth limit believed off. Instrument backgrounds not measured.',fontsize=13)
    fig.supxlabel('The 1 s and 10 s records are sparse scope samples; their scatter cannot be assigned to low-frequency noise.',fontsize=9)
    for ext in ['png','pdf']: fig.savefig(ROOT/'10-13Scope'/f'dc_noise_10_13.{ext}',dpi=180)
    plt.close(fig)

    path=ROOT/'10-13FRA/FRADAta.csv'
    log_frequency,gain_db,phase_deg=np.loadtxt(path,delimiter=',',skiprows=1).T
    f=10**log_frequency
    assert np.all(np.diff(f)>0) and 99<f[0]<101 and 9.9e6<f[-1]<10.1e6
    low=(f>=100)&(f<=1e4)
    gain0=float(np.median(gain_db[low]))
    fit_band=(f>=1e4)&(f<=1e6)
    slope,intercept=np.polyfit(f[fit_band],phase_deg[fit_band],1)
    delay_s=float(-slope/360)
    residual_deg=float(np.std(phase_deg[fit_band]-(slope*f[fit_band]+intercept)))
    below1m=(f>=100)&(f<=1e6)
    points=[]
    for target in [1e3,1e4,5e4,1e5,3.5e5,1e6,1e7]:
        points.append(dict(frequency_hz=target,gain_db=float(np.interp(np.log10(target),log_frequency,gain_db)),
            phase_deg=float(np.interp(np.log10(target),log_frequency,phase_deg))))
    fra=dict(file=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        frequency_column='log10(frequency_Hz)',low_frequency_gain_db=gain0,
        low_frequency_gain_V_per_V=float(10**(gain0/20)),
        gain_excursion_100Hz_1MHz_db=[float(np.min(gain_db[below1m])-gain0),float(np.max(gain_db[below1m])-gain0)],
        delay_fit_10kHz_1MHz_s=delay_s,phase_fit_residual_rms_deg=residual_deg,
        fitted_intercept_deg=float(intercept),points=points,
        caveat='One input grounded, static inversion removed only for display. Includes fixture/cable/reference delay; '
               'does not measure converter delay or additive output noise.')
    fig,axes=plt.subplots(2,1,sharex=True,figsize=(10,7),layout='constrained')
    axes[0].semilogx(f,gain_db,color='#1769aa',lw=.8,label='Measured gain')
    axes[0].axhline(gain0,color='gray',ls='--',label=f'{gain0:.3f} dB = {10**(gain0/20):.3f} V/V')
    axes[0].set(ylabel='Gain (dB)',ylim=(13.5,15.6))
    axes[1].semilogx(f,phase_deg+180,color='#27806b',lw=.8,label='Measured phase + 180°')
    axes[1].semilogx(f,slope*f+intercept+180,'--',color='#c85a26',
                     label=f'10 kHz–1 MHz fit: {delay_s*1e9:.2f} ns; residual {residual_deg:.2f}° RMS')
    axes[1].set(xlabel='Frequency (Hz)',ylabel='Phase after removing inversion (deg)',ylim=(-43,2),xlim=(100,1e7))
    for ax in axes:
        ax.axvline(5e4,color='gray',ls=':',alpha=.7)
        ax.grid(alpha=.2,which='both');ax.legend(fontsize=9)
    fig.suptitle('D2S FRA with one differential input grounded\n'
                 'Flat through 1 MHz; no gain or phase feature near 50 kHz',fontsize=13)
    fig.supxlabel('Delay includes the measured fixture. Static 180° is inversion, not a transit delay.',fontsize=9)
    for ext in ['png','pdf']:fig.savefig(ROOT/'10-13FRA'/f'd2s_fra_10_13.{ext}',dpi=180)
    plt.close(fig)
    summary=dict(conditions=dict(dac_code=100,blp_present=False,scope_coupling='DC',
                  scope_bandwidth_limit='believed off',controllers_connected=True,
                  scope_loading_changed_between_records=False),
                 mean_shift_TEK7_minus_TEK6_V=traces[2][2]['mean_V']-traces[1][2]['mean_V'],
                 scope=[r[2] for r in traces],analyzer=sa,fra=fra,
                 source_references=['https://www.keysight.com/content/dam/keysight/en/doc/ungate/data-sheets/5990-9783.pdf',
                                    'https://download.tek.com/manual/077044401web.pdf'])
    (ROOT/'10-13Scope/dc_and_fra_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'scope_rms_mV':[r[2]['fluctuation_rms_V']*1e3 for r in traces],
                     'gain_dB':gain0,'delay_ns':delay_s*1e9,'phase_fit_rms_deg':residual_deg},indent=2))


if __name__=='__main__': main()
