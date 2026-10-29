"""Full loop return ratio from measured plant and the two-phase RTL recurrence.

Offline only. Linear small-signal model: quantized coefficients, no rounding,
saturation, or anti-windup. Retains relative integral/shelf pipeline registers.
The supplied main-path delay is added once after removing the pure-P delay
from the lifted controller. No bitstream or hardware settings are changed.
"""
from pathlib import Path
import hashlib
import json
import os
import tempfile
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir())/'intensity_bode_mpl'))
os.environ.setdefault('XDG_CACHE_HOME', str(Path(tempfile.gettempdir())/'intensity_bode_cache'))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT/'ILAData'/'10-28'/'intensity_loop_171424_945111.csv'
if not DATA.exists():
    DATA = HERE/'raw_data'/DATA.name
FS = 245.76e6
PRESETS = json.loads((HERE/'controller_starting_points.json').read_text())
MODEL = json.loads((HERE/'analysis_summary.json').read_text())


def step(state, value, phase, alpha, gain_inf, shelf_alpha, order):
    """RTL old-state semantics; power units throughout, normalized Kp=1."""
    v = state.copy()
    i = state[:3]
    # indices3:6 increments;6:9 registered integral inputs;9:12 sum registers.
    v[6:9] = [state[12], state[12]+state[9], state[12]+state[10]]
    v[9:12] = [i[0], i[0]+i[1], sum(i[:order])]
    v[12] = value                        # registered Kp product, divided byKp
    v[13] = state[12]+state[11]          # registered proportional plusI output
    if phase == 0:
        v[3:6] = state[6:9]*alpha
    else:
        v[:3] = i+state[3:6]
    v[order:3] = 0                       # disabled integral states reset
    # Shelf states14:19 = state, increment, product, input_d, output.
    difference = state[13]-state[14]
    v[16] = (gain_inf-1)*difference
    v[17] = state[13]
    v[18] = state[17]+state[16]
    if phase == 0:
        v[15] = shelf_alpha*difference
    else:
        v[14] = state[14]+state[15]
    return v


def lifted_shape(f_hz, coefficients, shelf):
    """Fundamental response; also returns amplitude of the half-rate image."""
    order = len(coefficients['integrator_Q24'])
    alpha = np.array((coefficients['integrator_Q24']+[0,0,0])[:3])/2**24
    a_shelf = round(-np.expm1(-2*np.pi*200e3/(FS/2))*2**30)/2**30
    gain_inf = 10.0
    zero = np.zeros(19)
    eye = np.eye(19)
    matrices = []
    for phase in (0,1):
        b = step(zero, 1, phase, alpha, gain_inf, a_shelf, order)
        A = np.column_stack([step(eye[:,j], 0, phase, alpha, gain_inf, a_shelf, order)
                             for j in range(19)])
        matrices.append((A,b))
    A0,b0 = matrices[0]; A1,b1 = matrices[1]
    z = np.exp(2j*np.pi*np.asarray(f_hz)/FS)
    left = z[:,None,None]**2*eye - A1@A0
    right = (A1@b0)[None,:]+z[:,None]*b1
    before_even = np.linalg.solve(left, right[...,None])[...,0]
    after_even = before_even@A0.T+b0
    after_odd = after_even@A1.T+z[:,None]*b1
    output = 18 if shelf else 13
    same_frequency = (after_even[:,output]+after_odd[:,output]/z)/2
    image = (after_even[:,output]-after_odd[:,output]/z)/2
    # Under the update convention pureP isz^-1; through unity shelf it isz^-3.
    # Remove that common factor, then add the total measured-budget path once.
    remove_common = z**(3 if shelf else 1)
    delay = (13 if shelf else 11)/FS
    shape = same_frequency*remove_common*np.exp(-2j*np.pi*f_hz*delay)
    return shape, np.abs(image)/np.maximum(np.abs(same_frequency),1e-30)


def unwrap_phase(response):
    phase = np.unwrap(np.angle(response))*180/np.pi
    if phase[0] > 0:
        phase -= 360
    return phase


def crossings(f, response):
    """All unity and negative-real-axis crossings; no single-margin shortcut."""
    logf = np.log(f); db = 20*np.log10(abs(response)); phase = unwrap_phase(response)
    rows = []
    for i in np.flatnonzero(db[:-1]*db[1:] < 0):
        a = -db[i]/(db[i+1]-db[i])
        rows.append(dict(kind='unity_gain',frequency_hz=float(np.exp(logf[i]+a*(logf[i+1]-logf[i]))),
                         direction='down' if db[i+1]<db[i] else 'up',
                         phase_margin_deg=float(180+phase[i]+a*(phase[i+1]-phase[i]))))
    for level in np.arange(-180,-1261,-360):
        for i in np.flatnonzero((phase[:-1]-level)*(phase[1:]-level) < 0):
            a=(level-phase[i])/(phase[i+1]-phase[i])
            rows.append(dict(kind='negative_real_axis',frequency_hz=float(np.exp(logf[i]+a*(logf[i+1]-logf[i]))),
                             direction='down' if phase[i+1]<phase[i] else 'up',
                             interpretation='upper gain boundary' if phase[i+1]<phase[i] else 'lower gain boundary; not a gain-increase margin',
                             phase_level_deg=int(level),gain_margin_db=float(-db[i]-a*(db[i+1]-db[i]))))
    return sorted(rows,key=lambda r:r['frequency_hz'])


def main():
    sanity_f=np.array([100.,150e3,1e6])
    pure_p,image=lifted_shape(sanity_f,{'integrator_Q24':[0]},False)
    assert np.allclose(pure_p,np.exp(-2j*np.pi*sanity_f*11/FS),rtol=1e-10,atol=1e-10)
    assert max(image)<1e-10
    raw = pd.read_csv(DATA)
    f = np.unique(np.r_[np.geomspace(100,1e6,6000),raw.frequency_hz,150e3,300e3])
    fraw = raw.frequency_hz.to_numpy(); K = (raw.K_re+1j*raw.K_im).to_numpy()
    k0 = MODEL['plant_static_fractional_gain_per_code']
    measured = (f >= fraw.min()) & (f <= fraw.max())
    H = np.exp(-(f/MODEL['gaussian_amplitude_1e_frequency_hz'])**2
               -2j*np.pi*f*MODEL['effective_plant_delay_s'])
    H[measured] = np.exp(np.interp(np.log(f[measured]),np.log(fraw),np.log(abs(K/k0)))+
                        1j*np.interp(np.log(f[measured]),np.log(fraw),np.unwrap(np.angle(K))))
    curves, records = {}, []
    for kind in ('PI','PII','PIII'):
        preset = PRESETS[kind]
        gain = preset['kp_Q12']/4096
        for shelf in (False,True):
            shape,image_fraction = lifted_shape(f,preset,shelf)
            base = H*shape
            settings = [('fixed_gain',gain)]
            if shelf:
                target = preset['target_crossover_hz']
                retuned = round(4096/np.interp(target,f,abs(base)))/4096
                settings.append(('normalized_at_target',retuned))
            for family,g in settings:
                name=f'{family}_{kind}_{"lead" if shelf else "bypass"}'
                L=g*base; curves[name]=L
                record = dict(case=name,family=family,controller=kind,shelf_enabled=shelf,
                              proportional_gain=g,kp_Q12=round(g*4096),
                              integral_corners_hz=preset['integrator_corner_hz'],
                              lead_zero_hz=20000 if shelf else None,lead_pole_hz=200000 if shelf else None,
                              main_path_delay_s=(13 if shelf else 11)/FS,
                              target_normalization_frequency_hz=preset['target_crossover_hz'] if family=='normalized_at_target' else None,
                              measured_band_crossings=crossings(f[measured],L[measured]),
                              below_measurement_extrapolated_crossings=crossings(f[~measured],L[~measured]),
                              magnitude_at_1MHz=float(abs(L[-1])),
                              maximum_half_rate_image_amplitude_ratio_in_measured_band=float(max(image_fraction[measured])))
                records.append(record)
    # Separate alternatePI example: this also changes the integral corner to300kHz.
    alternate=PRESETS['PI_lead_300k']; shape,image=lifted_shape(f,alternate,True)
    curves['alternate_PI_300k_corner_lead']=H*shape*(alternate['kp_Q12']/4096)
    record=dict(case='alternate_PI_300k_corner_lead',family='alternate_PI_corner',controller='PI',
                shelf_enabled=True,proportional_gain=alternate['kp_Q12']/4096,kp_Q12=alternate['kp_Q12'],
                integral_corners_hz=alternate['integrator_corner_hz'],lead_zero_hz=20000,lead_pole_hz=200000,
                main_path_delay_s=13/FS,measured_band_crossings=crossings(f[measured],curves['alternate_PI_300k_corner_lead'][measured]),
                magnitude_at_1MHz=float(abs(curves['alternate_PI_300k_corner_lead'][-1])))
    records.append(record)

    frames=[]; margin_rows=[]
    for r in records:
        L=curves[r['case']]
        frames.append(pd.DataFrame(dict(case=r['case'],frequency_hz=f,plant_measured_band=measured,
                                       loop_real=L.real,loop_imag=L.imag,gain_db=20*np.log10(abs(L)),
                                       phase_unwrapped_deg=unwrap_phase(L))))
        for row in r['measured_band_crossings']:
            margin_rows.append(dict(case=r['case'],plant_measured_band=True,**row))
        for row in r.get('below_measurement_extrapolated_crossings',[]):
            margin_rows.append(dict(case=r['case'],plant_measured_band=False,**row))
    pd.concat(frames,ignore_index=True).to_csv(HERE/'open_loop_predictions.csv',index=False)
    pd.DataFrame(margin_rows).to_csv(HERE/'open_loop_margins.csv',index=False)
    payload=dict(plant_source=DATA.name,plant_source_sha256=hashlib.sha256(DATA.read_bytes()).hexdigest(),
                 measured_plant_frequency_range_hz=[float(fraw.min()),float(fraw.max())],
                 plant_delay_s=MODEL['effective_plant_delay_s'],
                 model='Exact two-phase linearized RTL recurrence with quantized coefficients; arithmetic rounding and saturation omitted; fundamental response only',
                 normalization='K(f)/K0, assuming exact local sensor/AOM inversion and correct effective incident-power scale',
                 extrapolation='100Hz to first measured frequency: fitted Gaussian magnitude and pure delay; dashed/unvalidated; no extrapolation above1MHz',
                 cases=records)
    (HERE/'open_loop_predictions.json').write_text(json.dumps(payload,indent=2)+'\n')

    for family, filename in [('fixed_gain','open_loop_fixed_gain.png'),
                             ('normalized_at_target','open_loop_normalized_gain.png'),
                             ('normalized_at_target','open_loop_normalized_zoom.png')]:
        zoom = 'zoom' in filename
        fig,axes=plt.subplots(2,3,figsize=(15,8),sharex=True,sharey='row',layout='constrained')
        for j,kind in enumerate(('PI','PII','PIII')):
            names=[f'fixed_gain_{kind}_bypass',f'{family}_{kind}_lead']
            for name,color in zip(names,('tab:blue','tab:orange')):
                L=curves[name];cfg=next(r for r in records if r['case']==name)
                label=('Shelf bypass' if not cfg['shelf_enabled'] else 'Lead 20/200 kHz')+f"; Kp={cfg['proportional_gain']:.6f}"
                for crossing in cfg['measured_band_crossings']:
                    if crossing['kind']=='unity_gain':
                        axes[0,j].plot(crossing['frequency_hz'],0,marker='v' if crossing['direction']=='down' else '^',
                                       color=color,ms=7,zorder=5)
                for a,y in ((axes[0,j],20*np.log10(abs(L))),(axes[1,j],unwrap_phase(L))):
                    a.semilogx(f[measured],y[measured],color=color,lw=1.8,label=label)
                    a.semilogx(f[~measured],y[~measured],color=color,lw=1.4,ls='--')
            corners=', '.join(f'{v/1e3:g} kHz' if v>=1e3 else f'{v:g} Hz' for v in PRESETS[kind]['integrator_corner_hz'])
            axes[0,j].set_title(f'{kind}: integral corners {corners}')
            axes[0,j].legend(fontsize=8,loc='upper right')
            axes[0,j].axhline(0,color='black',lw=.8)
            axes[1,j].axhline(-180,color='black',lw=.8)
            axes[1,j].set_xlabel('Frequency [Hz]')
            for a in axes[:,j]:
                a.axvspan(100,fraw.min(),color='.92',zorder=-3)
                a.grid(which='both',alpha=.25);a.set_xlim(1e4 if zoom else 100,1e6)
            axes[0,j].set_ylim((-12,12) if zoom else (-20,100));axes[1,j].set_ylim(-450,15)
        axes[0,0].set_ylabel('Open-loop return ratio |L| [dB]')
        axes[1,0].set_ylabel('Unwrapped phase of L [deg]')
        title=('Same Kp and integral corners: toggle the lead shelf (+20 dB at high frequency)' if family=='fixed_gain'
               else 'Shelf Kp adjusted to |L|≈1 at 300/150/150 kHz — inspect every crossing')
        subtitle=('Measured plant × complete digital controller; triangles mark unity crossings' if zoom else
                  'Measured plant × complete digital controller; dashed below 1 kHz is unvalidated extrapolation')
        fig.suptitle(title+'\n'+subtitle,fontsize=13)
        fig.savefig(HERE/filename,dpi=180);plt.close(fig)
    by_name={r['case']:r for r in records}
    lines=["# Predicted open-loop return ratios", "",
           "These are the full return ratios `L(f) = [K(f)/K0] C(f)`, not controller-only responses.",
           "The plant is the measured intensity actuator→optical-sensor transfer in `intensity_loop_171424_945111.csv`.",
           "The same local power-linearization assumption and calibrated AOM scale used for the presets are retained.", "",
           "The blue curves bypass the shelf. Orange uses the same unity-DC lead shelf in every case:",
           "`(1+s/(2π×20 kHz))/(1+s/(2π×200 kHz))`. It approaches a gain of10 (+20dB), so enabling it at unchanged Kp is a major gain change.", "",
           "## 1. Fixed preset gains and corners", "",
           "![Fixed gains](open_loop_fixed_gain.png)", "",
           "| Case | Actual Kp | Measured-band unity crossings: frequency, direction, local PM | High-frequency gain-increase margin |",
           "|---|---:|---|---|"]
    def table_row(r):
        gain=[v for v in r['measured_band_crossings'] if v['kind']=='unity_gain']
        phase=[v for v in r['measured_band_crossings'] if v['kind']=='negative_real_axis' and v['direction']=='down']
        gc='; '.join(f"{v['frequency_hz']/1e3:.2f} kHz {v['direction']}, {v['phase_margin_deg']:.1f}°" for v in gain) or 'None between 1 kHz and 1 MHz'
        gm='; '.join(f"{v['gain_margin_db']:+.2f} dB at {v['frequency_hz']/1e3:.1f} kHz" for v in phase) or 'Not observed'
        return f"| {r['case']} | {r['proportional_gain']:.6f} | {gc} | {gm} |"
    lines += [table_row(r) for r in records if r['family']=='fixed_gain']
    lines += ["", "At unchanged Kp all three shelf-enabled cases stay above unity through1MHz and have a negative gain-increase margin at their measured negative-real-axis crossing. These are unsuitable as simple drop-in settings. The data do not locate their eventual high-frequency unity crossover; no behavior beyond1MHz is asserted.", "",
              "## 2. Reduce shelf Kp to set |L|≈1 at the nominal target", "",
              "Only Kp changes here; each controller keeps its original integral corners. Coefficients are rounded to the actual Q12 gain register. Setting one frequency to unity does not guarantee a unique or stable crossover.", "",
              "![Gain adjusted at target](open_loop_normalized_gain.png)", "",
              "![Crossover zoom](open_loop_normalized_zoom.png)", "",
              "| Case | Actual Kp | All measured-band unity crossings | High-frequency gain-increase margin |",
              "|---|---:|---|---|"]
    lines += [table_row(r) for r in records if r['family']=='normalized_at_target']
    lines += ["", "The PI50kHz-corner case crosses downward near6.4kHz, upward near300kHz, then downward again near754kHz. Its attractive local PM at the upward300kHz crossing is not a stable300kHz loop: the later down-crossing has negative PM and the measured phase-crossing margin is negative. PII/PIII with reduced Kp have one observed downward crossing near149kHz and much larger local phase margin, but gain margin falls from about5.1dB to2.85dB. They also give up low-frequency gain because Kp is reduced.", "",
              "The separately exported `PI_lead_300k` preset additionally changes the PI corner from50kHz to300kHz. It is therefore not one of the fixed-corner toggles above. For reference:", "",
              "| Different-corner comparison | Kp | Measured-band unity crossings | Gain-increase margin |",
              "|---|---:|---|---|",table_row(by_name['alternate_PI_300k_corner_lead']), "",
              "## Registered-controller model and limits", "",
              "The controller is evaluated from a two-phase lifted linear recurrence of the current RTL. It includes quantized Kp/integral/shelf coefficients, input registers before integral multipliers, alternate multiply/update clocks, registered integral sums, and shelf-state/output registers. The fundamental response is formed from both clock phases. An independent comparison against the bit-exact sequential reference agreed within1.03×10⁻⁶ relative complex error for tested PI/PII/PIII points with shelf on/off. Arithmetic rounding, saturation and anti-windup are omitted from the lifted small-signal model.", "",
              "The common pure-P pipeline factor is removed from that recurrence before adding the full calibrated-path budget:11 clocks=44.759ns, or13 clocks=52.897ns with the shelf. Thus the main delay is included once. The measured plant already includes the INT2 receive filter and has effective delay1.087µs. Feedforward does not enter the fixed-operating-point return ratio.", "",
              "Earlier preset JSON/README margins used the simpler product of half-rate PI factors plus the main delay. The refined relative-register model reduces the PI response magnitude only about0.31% around300kHz. Because its gain curve is almost flat near unity, that shifts its predicted crossing from299kHz to264kHz and changes local PM from48° to61°, while the gain-increase margin remains only about0.19dB. This is a sensitivity of the model, not a demonstrated hardware bandwidth change. The original large-dither FRA and calibration uncertainties are larger than this small magnitude difference; a new small-signal FRA must establish the actual crossing. PII/PIII predictions change much less. The programmed preset coefficients are unchanged.", "",
              "Solid curves use log-frequency interpolation of measured complex plant data from1kHz to1MHz. Below1kHz, dashed curves use the fitted Gaussian magnitude and pure delay; this region is unvalidated. No high-frequency extrapolation is drawn. Low-frequency PIII phase crosses−180° upward in that extrapolated region. Its negative numerical gain margin denotes a lower gain boundary in the assumed model, not the high-frequency gain-increase margin; taking the minimum of all signed margins would be misleading. Crossing directions and measured/extrapolated provenance are retained in the CSV/JSON. Full stability requires the Nyquist topology and plant behavior outside the measured band, not a single local phase-margin number.", "",
              "The CSV contains frequency, complexL, gain, unwrapped phase and a measured-band flag for every case. `open_loop_margins.csv` lists every crossing; `open_loop_predictions.json` records coefficients and model provenance. Regenerate with `python plot_open_loop_predictions.py` (NumPy, Pandas, Matplotlib). No hardware settings or preset files are modified.", ""]
    (HERE/'open_loop_predictions.md').write_text('\n'.join(lines))
    print(json.dumps(records,indent=2))


if __name__=='__main__':main()
