"""Predict intensity tracking with/without calibrated feedforward.

Run here with Python, NumPy, SciPy and Matplotlib. Numba is optional acceleration.
This is a nonlinear plant/controller simulation, not a bit-exact RTL simulation.
No board connection or register writes. All powers are in mW, times in seconds.
"""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
from scipy.signal import lfilter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def desired_power(time_s, smooth_shot=False):
    """8–18 mW operating region keeps nominal RF commands above 4000 codes."""
    t = time_s * 1e6
    p = np.full(len(t), 8.)
    if smooth_shot:
        transitions = ((50,100,8,18),(150,200,18,10),(250,300,10,15),
                       (350,400,15,9),(450,500,9,12),(550,650,12,0))
    else:
        transitions = ((50, 100, 8, 18), (150, 200, 18, 10), (550, 600, 9, 12))
    for start, stop, initial, final in transitions:
        mask = (t >= start) & (t < stop)
        p[t >= stop] = final
        p[mask] = initial + (final-initial)*.5*(1-np.cos(np.pi*(t[mask]-start)/(stop-start)))
    if not smooth_shot:
        p[(t >= 100) & (t < 150)] = 18
        p[(t >= 200) & (t < 250)] = 10
        p[(t >= 250) & (t < 400)] = 15
        p[(t >= 400) & (t < 550)] = 9
        p[(t >= 800) & (t < 900)] = 0
        p[t >= 900] = 12
    return p


def simulate_kernel(reference, noise, dt, weights, first_lag, gain, rates,
                    feedforward, actual_scale, estimated_scale, alpha, maximum_command,
                    sensor_min, sensor_max):
    """Forward integration of cascaded PI factors, conditional rail antiwindup.

    A delayed Gaussian FIR supplies measured plant magnitude AND mean delay;
    its centroid is the total measured delay, so delay is not counted twice.
    Initial integral bias gives the same settled state for both FF choices.
    """
    count = len(reference)
    lag = first_lag + len(weights)-1
    history = np.full(count+lag, reference[0])
    power = np.empty(count)
    measured_power = np.empty(count)
    command = np.empty(count)
    rail = np.zeros(count, dtype=np.bool_)
    sensor_outside = np.zeros(count, dtype=np.bool_)
    states = np.zeros(len(rates))
    # At exact steady state each preceding factor must have zero output to
    # avoid charging the next integrator. Put the required bias in the LAST.
    states[-1] = reference[0]*estimated_scale/actual_scale-feedforward*reference[0]
    inputs = np.zeros(len(rates))
    maximum_fraction = math.sin(alpha*maximum_command)**2
    power_step = 200./65536
    for n in range(count):
        measured = 0.
        for j in range(len(weights)):
            measured += weights[j]*history[n+lag-first_lag-j]
        power[n] = measured
        sensor_outside[n] = reference[n] > 0 and (measured+noise[n] < sensor_min or measured+noise[n] > sensor_max)
        sensed = min(sensor_max, max(sensor_min, measured+noise[n]))
        sensed = round(sensed/power_step)*power_step
        measured_power[n] = sensed
        error = reference[n]-sensed
        signal = max(-400., min(400., gain*error))
        for j in range(len(states)):
            inputs[j] = signal
            signal = max(-400., min(400., signal+states[j]))
        virtual_power = signal + feedforward*reference[n]
        fraction = virtual_power/estimated_scale
        upper = fraction >= maximum_fraction
        lower = fraction <= 0
        if reference[n] == 0:
            u = 0.
            for j in range(len(states)):
                states[j] = 0.
        else:
            rail[n] = upper or lower
            fraction = min(maximum_fraction, max(0., fraction))
            fraction = round(fraction*65536)/65536
            u = min(maximum_command, round(math.asin(math.sqrt(fraction))/alpha))
            for j in range(len(states)):
                increment = dt*rates[j]*inputs[j]
                if not ((upper and increment > 0) or (lower and increment < 0)):
                    states[j] = min(400., max(-400., states[j]+increment))
        command[n] = u
        history[n+lag] = actual_scale*math.sin(alpha*u)**2
    return power, command, rail, sensor_outside, measured_power


try:
    from numba import njit
    simulate_fast = njit(cache=True)(simulate_kernel)
except ImportError:
    simulate_fast = simulate_kernel


def simulate(preset, model, *, feedforward, scale_error=0., noise_rms_mW=0., dt_s=1/245.76e6,
             smooth_shot=False):
    duration_s = .75e-3 if smooth_shot else 1.1e-3
    time_s = np.arange(round(duration_s/dt_s))*dt_s
    reference = np.rint(desired_power(time_s, smooth_shot)/model['power_quantization_mW'])*model['power_quantization_mW']
    sigma_s = 1/(np.sqrt(2)*np.pi*model['gaussian_amplitude_1e_frequency_hz'])
    mean_s = model['effective_plant_delay_s']+model['added_core_and_probe_delay_s']
    lo = max(1, int(np.floor((mean_s-5*sigma_s)/dt_s)))
    hi = int(np.ceil((mean_s+5*sigma_s)/dt_s))
    lags = np.arange(lo, hi+1)
    kernel = np.exp(-.5*((lags*dt_s-mean_s)/sigma_s)**2)
    kernel /= kernel.sum()
    assert abs(float(np.dot(kernel, lags*dt_s))-mean_s) < dt_s/100
    noise = np.zeros(len(time_s))
    if noise_rms_mW:
        # Assumed detector noise, not a noise estimate from the uploaded data.
        raw = np.random.default_rng(20261028).normal(size=len(time_s))
        a = np.exp(-2*np.pi*1e6*dt_s)
        noise = lfilter([1-a], [1, -a], raw)
        noise *= noise_rms_mW/np.std(noise)
    gain = preset['kp_Q12']/4096
    rates = np.asarray(preset['integrator_Q24'], float)/2**24*122.88e6
    values = simulate_fast(reference, noise, dt_s, kernel, lo, gain, rates,
                           float(feedforward), model['estimated_effective_input_power_mW']*(1+scale_error),
                           model['estimated_effective_input_power_mW'],
                           model['alpha_rad_per_code'], 21335.,
                           model['sensor_min_mW'], model['sensor_max_mW'])
    return dict(time_s=time_s, reference_mW=reference, power_mW=values[0],
                command_codes=values[1], clipped=values[2], sensor_outside=values[3],
                measured_mW=values[4], sensor_min_mW=model['sensor_min_mW'], smooth_shot=smooth_shot)


def metrics(record):
    t = record['time_s']*1e6
    error = record['power_mW']-record['reference_mW']
    ramp_windows = ((50,100),(150,200),(550,600))
    steady_windows = ((120,145),(220,245),(330,390),(470,540),(680,780),(1000,1100))
    edge_times = (250,400,800,900)
    if record['smooth_shot']:
        ramp_windows = ((50,100),(150,200),(250,300),(350,400),(450,500),(550,650))
        steady_windows = ((20,45),(120,145),(220,245),(320,345),(420,445),(520,545))
        edge_times = ()
    ramps = np.zeros(len(t), bool)
    for start, stop in ramp_windows:
        ramps |= (t >= start) & (t < stop)
    edges = np.zeros(len(t), bool)
    for start in edge_times:
        edges |= (t >= start) & (t < start+30)
    steady = np.zeros(len(t), bool)
    for start, stop in steady_windows:
        steady |= (t >= start) & (t < stop)
    rms = lambda mask: float(np.sqrt(np.mean(error[mask]**2))) if mask.any() else None
    bright = record['reference_mW'] > 0
    valid = ~record['sensor_outside'] & ~record['clipped']
    metric_mask = bright & valid
    indices = np.arange(len(t))
    rises = bright & np.r_[False, ~bright[:-1]]
    last_rise = np.maximum.accumulate(np.where(rises, indices, -len(t)))
    since_rise_us = (indices-last_rise)*(t[1]-t[0])
    startup = bright & record['sensor_outside'] & ~record['clipped'] & (last_rise >= 0) & (since_rise_us < 10) & (record['power_mW'] < record['sensor_min_mW'])
    excluded_fraction = float(startup.sum()/bright.sum())
    comparable = record['measured_mW']-record['reference_mW']
    return dict(rms_all_mW=rms(np.ones(len(t), bool)), rms_ramps_mW=rms(ramps),
                rms_abrupt_edges_mW=rms(edges), rms_bright_steady_mW=rms(steady),
                maximum_absolute_error_mW=float(np.max(np.abs(error))),
                maximum_power_mW=float(np.max(record['power_mW'])),
                maximum_command_codes=float(np.max(record['command_codes'])),
                command_rail_fraction=float(np.mean(record['clipped'])),
                sensor_outside_calibration_bright_fraction=float(record['sensor_outside'].sum()/bright.sum()),
                rms_calibrated_valid_illuminated_mW=float(np.sqrt(np.mean(comparable[metric_mask]**2))),
                optimizer_usable=bool((valid | startup).all() and not record['clipped'].any() and excluded_fraction <= .001),
                excluded_startup_fraction=excluded_fraction,
                calibrated_illuminated_fraction=float(metric_mask.sum()/bright.sum()))


def main():
    summary = json.loads((HERE/'analysis_summary.json').read_text())
    aom = json.loads((HERE/'aom_model.json').read_text())
    presets = json.loads((HERE/'controller_starting_points.json').read_text())
    model = dict(effective_plant_delay_s=summary['effective_plant_delay_s'],
                 added_core_and_probe_delay_s=presets['PI']['additional_fast_path_delay_s'],
                 gaussian_amplitude_1e_frequency_hz=summary['gaussian_amplitude_1e_frequency_hz'],
                 alpha_rad_per_code=aom['alpha_rad_per_code'],
                 sensor_min_mW=summary['sensor_maps']['low_power']['power_range_mW'][0],
                 sensor_max_mW=summary['sensor_maps']['low_power']['power_range_mW'][1],
                 estimated_effective_input_power_mW=summary['effective_optical_scale_at_FRA_mW'], maximum_command_codes=21335,
                 power_quantization_mW=200/65536, timestep_s=1/245.76e6)
    names = ['PI', 'PI_150k_fallback', 'PII', 'PIII']
    assert all(not presets[name]['lead_lag_enabled'] and
               presets[name]['additional_fast_path_delay_s'] == model['added_core_and_probe_delay_s']
               for name in names), 'This comparison models the common shelf-bypassed pipeline.'
    rows, smooth_rows, plotted, convergence = [], [], {}, []
    for name in names:
        for scale_error, noise in ((-.05, 0.), (0., 0.), (.05, 0.), (0., .005)):
            for ff in (False, True):
                record = simulate(presets[name], model, feedforward=ff,
                                  scale_error=scale_error, noise_rms_mW=noise)
                row = dict(controller=name, feedforward=ff, scale_error_fraction=scale_error,
                           assumed_detector_noise_rms_mW=noise, **metrics(record))
                rows.append(row)
                if noise == 0:
                    smooth = simulate(presets[name], model, feedforward=ff,
                                      scale_error=scale_error, smooth_shot=True)
                    smooth_rows.append(dict(controller=name, feedforward=ff,
                                            scale_error_fraction=scale_error, **metrics(smooth)))
                print(name, ff, scale_error, noise, row['rms_all_mW'], flush=True)
                if scale_error == 0 and noise == 0:
                    plotted[name, ff] = record
                    fine = simulate(presets[name], model, feedforward=ff, dt_s=model['timestep_s']/2)
                    fine_metrics = metrics(fine)
                    difference = fine['power_mW'][::2]-record['power_mW']
                    convergence.append(dict(controller=name, feedforward=ff,
                        rms_waveform_difference_mW=float(np.sqrt(np.mean(difference**2))),
                        rms_all_change_fraction=fine_metrics['rms_all_mW']/row['rms_all_mW']-1,
                        fine_rms_all_mW=fine_metrics['rms_all_mW']))
    output = dict(model=model, results=rows, smooth_shot_results=smooth_rows, convergence=convergence,
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                       (HERE/'aom_model.json', HERE/'analysis_summary.json', HERE/'controller_starting_points.json')},
        interpretation='Modeled calibrated measured-power timeline; no retrospective delay alignment. '
                       'Combined measured delay cannot identify separate optical and sensor delays.')
    (HERE/'tracking_simulation.json').write_text(json.dumps(output, indent=2))
    plt.rcParams.update({'font.size':10})
    fig, axes = plt.subplots(3, 2, figsize=(13, 11), constrained_layout=True)
    colors = {False:'#b24a35', True:'#2166ac'}
    for ff in (False, True):
        r = plotted['PI_150k_fallback', ff]; t = r['time_s']*1e6
        axes[0, 0].plot(t[::20], r['power_mW'][::20], color=colors[ff], label=f'FF {"on" if ff else "off"}')
        axes[0, 1].plot(t[::20], (r['power_mW']-r['reference_mW'])[::20], color=colors[ff])
        for col, name in enumerate(('PI', 'PI_150k_fallback')):
            r = plotted[name, ff]; mask=(r['time_s']>=245e-6)&(r['time_s']<300e-6)
            axes[1, col].plot(r['time_s'][mask]*1e6, r['power_mW'][mask], color=colors[ff])
    r = plotted['PI_150k_fallback', False]
    axes[0,0].plot(r['time_s'][::20]*1e6, r['reference_mW'][::20], 'k--', lw=1, label='Desired')
    axes[0,0].set(xlim=(30,225), ylim=(7,19), ylabel='Power [mW]', title='Smooth ramps, PI 150 kHz fallback'); axes[0,0].legend()
    ramp_mask = (r['time_s']>=30e-6)&(r['time_s']<225e-6)
    error_limit = 1.1*max(np.max(np.abs((plotted['PI_150k_fallback',ff]['power_mW']-
                         plotted['PI_150k_fallback',ff]['reference_mW'])[ramp_mask])) for ff in (False,True))
    axes[0,1].set(xlim=(30,225), ylim=(-error_limit,error_limit), ylabel='Power − desired [mW]', title='Same physical timeline; no alignment shift')
    for col, name in enumerate(('PI', 'PI_150k_fallback')):
        r = plotted[name, False]; mask=(r['time_s']>=245e-6)&(r['time_s']<300e-6)
        axes[1,col].plot(r['time_s'][mask]*1e6,r['reference_mW'][mask],'k--',lw=1)
        axes[1,col].set(ylabel='Power [mW]',title=f'Abrupt 10→15 mW step: {"300 kHz PI" if col==0 else "150 kHz PI"}')
    x=np.arange(len(names)); labels=['PI 300k','PI 150k','PII 150k','PIII 150k']
    for ff in (False,True):
        selected=[next(z for z in smooth_rows if z['controller']==name and z['feedforward']==ff and z['scale_error_fraction']==0) for name in names]
        axes[2,0].bar(x+(.18 if ff else -.18),[z['rms_all_mW'] for z in selected],width=.36,color=colors[ff],label=f'FF {"on" if ff else "off"}')
    axes[2,0].set(xticks=x,xticklabels=labels,ylabel='Smooth-shot RMS error [mW]',title='Separate smooth shot, including ramp to zero');axes[2,0].legend()
    for name,label in zip(names,labels):
        ratios=[]; both_railed=[]
        for mismatch in (-.05,0,.05):
            pair=[next(z for z in rows if z['controller']==name and z['feedforward']==ff and z['scale_error_fraction']==mismatch and z['assumed_detector_noise_rms_mW']==0) for ff in (False,True)]
            ratios.append(pair[1]['rms_all_mW']/pair[0]['rms_all_mW'])
            both_railed.append(all(z['command_rail_fraction']>.01 for z in pair))
        axes[2,1].plot([-5,0,5],ratios,'o-',label=label)
        if any(both_railed):
            mask=np.array(both_railed)
            axes[2,1].scatter(np.array([-5,0,5])[mask],np.array(ratios)[mask],marker='x',
                              s=100,c='black',zorder=5,label='Both runs rail >1%')
    axes[2,1].axhline(1,color='k',ls='--',lw=1);axes[2,1].set(xlabel='Actual input-power scale error [%]',ylabel='RMS with FF / RMS without FF',title='Mixed shot: below 1 is better\n300 kHz PI at +5% rails: not a linear-response score');axes[2,1].legend(fontsize=8)
    for ax in axes[:2].ravel():ax.set_xlabel('Time [µs]')
    for ax in axes.ravel():ax.grid(alpha=.25)
    fig.suptitle('Predicted calibrated intensity tracking — fixed controller within each FF comparison\nFitted plant and quantized maps; numerical model, not hardware validation',fontsize=13)
    fig.savefig(HERE/'tracking_simulation.png',dpi=170)
    write_report(rows, smooth_rows, convergence, model)


def write_report(rows, smooth_rows, convergence, model):
    names = ('PI', 'PI_150k_fallback', 'PII', 'PIII')
    def pair(data, name, scale=0., noise=0.):
        return [next(z for z in data if z['controller'] == name and z['feedforward'] == ff
                     and z['scale_error_fraction'] == scale
                     and z.get('assumed_detector_noise_rms_mW', 0.) == noise) for ff in (False, True)]
    lines = ['# Feedforward tracking simulation', '',
        'Feedforward adds the desired optical power to the controller correction **before** the shared incident-power scale and sin² inverse. It is enabled by control bit 2. It provides no advance knowledge of the shot and does not compensate propagation delay.', '',
        'Comparisons use identical controller settings within each feedforward toggle. Both cases start from the same settled 8 mW state; the final integral bias differs to preserve that operating point. The mixed shot contains smooth 8–18 mW ramps, abrupt 10→15 and 15→9 mW steps, a 100 µs off interval, and restart to 12 mW. A separate smooth shot replaces the abrupt transitions with cosine ramps and ends with a smooth ramp to zero. No trace is shifted retrospectively.', '',
        '| Controller | Smooth shot FF off/on RMS [mW] | Mixed shot FF off/on RMS [mW] | Mixed ramp ratio on/off | Abrupt-edge ratio on/off |',
        '|---|---:|---:|---:|---:|']
    for name in names:
        a, b = pair(rows, name); sa, sb = pair(smooth_rows, name)
        lines.append(f"| {name} | {sa['rms_all_mW']:.5f} / {sb['rms_all_mW']:.5f} | {a['rms_all_mW']:.5f} / {b['rms_all_mW']:.5f} | {b['rms_ramps_mW']/a['rms_ramps_mW']:.3f} | {b['rms_abrupt_edges_mW']/a['rms_abrupt_edges_mW']:.3f} |")
    lines += ['', 'Primary whole-shot RMS uses modeled readout-band power minus desired power over the entire physical timeline, including off/restart delay. It includes no detector noise in the scoring quantity; assumed detector noise still drives the feedback loop. Separate steady, ramp, edge, clipping and calibration-range metrics are saved in JSON. A better ramp score does not imply better step overshoot or stability.', '',
        'The optimizer instead scores **calibrated measured-power RMS over valid illuminated samples**. The following diagnostic uses that same sample definition, including detector noise and excluding invalid readings. Only below-range startup lasting at most 10 µs is eligible for grace, with an overall 0.1% illuminated-sample limit. Persistent range errors or any clipping disqualify optimization even if a diagnostic RMS can be calculated. These simulated flags have no DMA decimation-interval ambiguity.', '',
        '| Controller | Calibrated illuminated RMS FF off/on [mW] | Optimizer usable off/on | Excluded startup fraction off/on |',
        '|---|---:|---|---:|']
    for name in names:
        a, b = pair(rows, name)
        lines.append(f"| {name} | {a['rms_calibrated_valid_illuminated_mW']:.5f} / {b['rms_calibrated_valid_illuminated_mW']:.5f} | {a['optimizer_usable']} / {b['optimizer_usable']} | {a['excluded_startup_fraction']:.5f} / {b['excluded_startup_fraction']:.5f} |")
    lines += ['', '## Robustness cases', '',
        '| Controller | Smooth-shot FF ratio at −5% / 0 / +5% scale error | Mixed-shot ratio at −5% / 0 / +5% | With assumed 5 µW noise: mixed ratio | Maximum rail fraction across cases |',
        '|---|---|---|---:|---:|']
    for name in names:
        def ratios(data):
            return ' / '.join(f"{b['rms_all_mW']/a['rms_all_mW']:.3f}" for a, b in (pair(data, name, scale) for scale in (-.05, 0., .05)))
        a, b = pair(rows, name, noise=.005)
        rail = max(z['command_rail_fraction'] for z in rows if z['controller'] == name)
        lines.append(f"| {name} | {ratios(smooth_rows)} | {ratios(rows)} | {b['rms_all_mW']/a['rms_all_mW']:.3f} | {rail:.4f} |")
    lines += ['', 'The 300 kHz PI at +5% scale error rails with both feedforward choices in both waveforms. Its ratios describe finite-duration nonlinear transients, not a usable improvement or a stable operating point.']
    quiet_off, quiet_on = pair(rows, 'PI_150k_fallback', noise=.005)
    lines += ['', f"With the assumed detector noise, the 150 kHz PI's steady modeled power noise is {1000*quiet_off['rms_bright_steady_mW']:.3f} µW RMS without FF and {1000*quiet_on['rms_bright_steady_mW']:.3f} µW with FF. Thus feedforward improves commanded-ramp tracking here without suppressing or appreciably adding steady detector-driven noise."]
    lines += ['', 'Feedforward changes the reference response, not the small-signal feedback characteristic equation at fixed operating power. It can excite a weakly damped loop more strongly. The 300 kHz PI preset has only about 0.17 dB modeled gain margin, so a +5% optical-scale error can change stability. The 150 kHz fallback, PII and PIII have about 5 dB modeled gain margin. Growing oscillations, range failures or sustained clipping invalidate a linear-performance interpretation.', '',
        '## Physical assumptions and limits', '',
        f"- Plant impulse response: positive causal Gaussian, mean {(model['effective_plant_delay_s']+model['added_core_and_probe_delay_s'])*1e6:.6f} µs; magnitude exp[−(f/{model['gaussian_amplitude_1e_frequency_hz']/1e6:.6f} MHz)²]. Its centroid already includes the measured 1.087 µs delay plus {model['added_core_and_probe_delay_s']*1e9:.3f} ns new processing; no additional smoothing delay is added. The kernel is truncated at ±5 sigma and normalized to unity DC.",
        '- The FRA includes the receiver/filter. Its combined delay cannot distinguish earlier actual optical power from subsequent sensing delay. The simulated waveform is the effective readout-band power; a separate optical timing measurement is needed to infer the physical field earlier in the chain.',
        f"- AOM: P=A_eff sin²(alpha u), with fitted alpha and its inverse. Estimated A_eff={model['estimated_effective_input_power_mW']:.3f} mW comes from the FRA operating point; actual A_eff is varied by ±5%. Bright targets of 8–18 mW keep nominal commands above 4000. The final smooth ramp to zero traverses lower commands where the AOM fit is less reliable; its final optical tail is a model extrapolation, not a validated low-power calibration. Maximum command 21335 is within the measured upper range.",
        '- Common optical units are 200 mW/65536. Desired power, sensed power, inverse fraction and DAC command are quantized. Sensor output is clipped to the measured low-mode calibration interval; excursions are reported rather than silently treated as valid. Zero target resets all integrators and commands zero.',
        '- PI/PII/PIII use cascaded PI factors with the quantized preset gains. Numerical integral states use directional antiwindup and ±400 mW state/output limits. Pipeline delay is aggregated into the plant. The exact RTL side-path timing and saturation sample ordering are approximated; separate bit-exact tests establish digital arithmetic and latency.',
        '- Added detector noise is explicitly assumed: 5 µW RMS with first-order 1 MHz bandwidth. It is not a measurement of this instrument. The same realization is used for each FF comparison. The other cases have quantization but no random detector noise.',
        '- The inverse has the same fitted sin² shape as the plant; the ±5% scale cases test calibration normalization error, not arbitrary shape error or extra RF resonances. Large-modulation source FRA data must be checked using a smaller perturbation. Dynamics above the measured 1 MHz band are an extrapolation.',
        '- The 1.1 ms mixed shot does not establish the long-term benefit of the 100 Hz PIII factor. Slow drift, run-to-run gain adaptation and preset switching are outside this simulation.', '',
        'The smooth-to-zero shot deliberately enters the uncalibrated sensor floor before becoming exactly zero. Its optimizer qualification is therefore false, as it should be; the reported smooth-shot RMS is a model prediction, not an assertion that the hardware optimizer would accept that record. Extend the low-power calibration or use a defined final off transition for a qualified experimental score.', '',
        '## Numerical check', '',
        f"Main timestep {model['timestep_s']*1e9:.6f} ns; all nominal mixed-shot cases repeated at half timestep. Largest change in whole-shot RMS: {100*max(abs(x['rms_all_change_fraction']) for x in convergence):.3f}%. Largest waveform RMS difference: {max(x['rms_waveform_difference_mW'] for x in convergence):.6f} mW. Quantization changes individual sample sequences, so waveform differences need not decrease monotonically.", '',
        'Run `python tracking_simulation.py` here to regenerate the compact JSON, plot and descriptor. It reads adjacent fitted-model/preset files and never accesses hardware. NumPy, SciPy and Matplotlib are required; Numba is optional acceleration. High-rate arrays are not exported.', '']
    (HERE/'tracking_simulation.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
