"""Compare PI reference tracking with identical disturbance-rejection dynamics.

No hardware access. Reuses the fitted model and shot from tracking_simulation.py.
Only the proportional reference weight changes; the integral sees full error.
Run here with Python, NumPy, SciPy and Matplotlib; Numba is optional acceleration.
"""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tracking_simulation import desired_power, metrics

HERE = Path(__file__).resolve().parent


def pi_kernel(reference, dt_s, weights, first_lag, kp, integral_rate_s,
              feedforward, beta, effective_power_mW, alpha_rad_per_code,
              maximum_command, sensor_min_mW, sensor_max_mW):
    """u_virtual=FF*r+Kp*(beta*r-y)+I; dI/dt=Kp*omega_i*(r-y).

    Keeping the full reference error in dI/dt is essential: weighting both
    terms would change the intended controller and its steady-state setpoint.
    """
    count = len(reference)
    lag = first_lag+len(weights)-1
    history = np.full(count+lag, reference[0])
    power, sensed, command = np.empty(count), np.empty(count), np.empty(count)
    rail, outside = np.zeros(count, np.bool_), np.zeros(count, np.bool_)
    integral = reference[0]*(1-feedforward-kp*(beta-1))
    fraction_limit = math.sin(alpha_rad_per_code*maximum_command)**2
    power_step_mW = 200./65536
    for n in range(count):
        y = 0.
        for j in range(len(weights)):
            y += weights[j]*history[n+lag-first_lag-j]
        power[n] = y
        outside[n] = reference[n] > 0 and (y < sensor_min_mW or y > sensor_max_mW)
        measured = round(min(sensor_max_mW, max(sensor_min_mW, y))/power_step_mW)*power_step_mW
        sensed[n] = measured
        proportional = max(-400., min(400., kp*(beta*reference[n]-measured)))
        feedback = max(-400., min(400., proportional+integral))
        fraction = (feedforward*reference[n]+feedback)/effective_power_mW
        high, low = fraction >= fraction_limit, fraction <= 0
        if reference[n] == 0:
            u, integral = 0., 0.
        else:
            rail[n] = high or low
            fraction = round(min(fraction_limit, max(0., fraction))*65536)/65536
            u = min(maximum_command, round(math.asin(math.sqrt(fraction))/alpha_rad_per_code))
            increment = dt_s*kp*integral_rate_s*(reference[n]-measured)
            if not ((high and increment > 0) or (low and increment < 0)):
                integral = min(400., max(-400., integral+increment))
        command[n] = u
        history[n+lag] = effective_power_mW*math.sin(alpha_rad_per_code*u)**2
    return power, sensed, command, rail, outside


try:
    from numba import njit
    run_kernel = njit(cache=True)(pi_kernel)
except ImportError:
    run_kernel = pi_kernel


def simulate(preset, model, feedforward, beta, dt_s):
    t = np.arange(round(1.1e-3/dt_s))*dt_s
    reference = np.rint(desired_power(t)/model['power_quantization_mW'])*model['power_quantization_mW']
    sigma_s = 1/(np.sqrt(2)*np.pi*model['gaussian_amplitude_1e_frequency_hz'])
    delay_s = model['effective_plant_delay_s']+preset['additional_fast_path_delay_s']
    first_lag = max(1, int(np.floor((delay_s-5*sigma_s)/dt_s)))
    last_lag = int(np.ceil((delay_s+5*sigma_s)/dt_s))
    lags = np.arange(first_lag, last_lag+1)
    weights = np.exp(-.5*((lags*dt_s-delay_s)/sigma_s)**2)
    weights /= weights.sum()
    assert len(preset['integrator_Q24']) == 1 and not preset['lead_lag_enabled']
    kp = preset['kp_Q12']/4096
    integral_rate_s = preset['integrator_Q24'][0]/2**24*122.88e6
    power, sensed, command, rail, outside = run_kernel(
        reference, dt_s, weights, first_lag, kp, integral_rate_s,
        float(feedforward), beta, model['estimated_effective_input_power_mW'],
        model['alpha_rad_per_code'], model['maximum_command_codes'],
        model['sensor_min_mW'], model['sensor_max_mW'])
    return dict(time_s=t, reference_mW=reference, power_mW=power, measured_mW=sensed,
                command_codes=command, clipped=rail, sensor_outside=outside,
                sensor_min_mW=model['sensor_min_mW'], smooth_shot=False)


def rising_edge_metrics(record, start_us, stop_us):
    """10–90% first rise, peak overshoot, and persistent ±2% settling.

    Thresholds use step height. Settling must hold until the next transition;
    None means the trace did not settle within the available record interval.
    """
    time_us = record['time_s']*1e6
    indices = np.flatnonzero((time_us >= start_us) & (time_us < stop_us))
    initial = record['reference_mW'][indices[0]-1]
    final = record['reference_mW'][indices[0]]
    step = final-initial
    assert step > 0
    t = time_us[indices]-start_us
    y = record['power_mW'][indices]

    def crossing(level):
        hits = np.flatnonzero(y >= initial+level*step)
        if not len(hits):
            return None
        k = hits[0]
        if k == 0:
            return float(t[0])
        return float(t[k-1]+(t[k]-t[k-1])*(initial+level*step-y[k-1])/(y[k]-y[k-1]))

    t10, t90 = crossing(.1), crossing(.9)
    bad = np.flatnonzero(np.abs(y-final) > .02*step)
    settled_us = float(t[bad[-1]+1]) if len(bad) and bad[-1]+1 < len(t) else None
    if not len(bad):
        settled_us = float(t[0])
    return dict(initial_mW=float(initial), final_mW=float(final),
                command_to_10_percent_us=t10, command_to_90_percent_us=t90,
                rise_10_to_90_us=None if t10 is None or t90 is None else t90-t10,
                overshoot_percent=float(100*(y.max()-final)/step),
                peak_power_mW=float(y.max()), settling_2_percent_us=settled_us,
                interval_rms_error_mW=float(np.sqrt(np.mean((y-final)**2))))


def main():
    source = json.loads((HERE/'tracking_simulation.json').read_text())
    model = source['model']
    presets = json.loads((HERE/'controller_starting_points.json').read_text())
    labels = ('FF off', 'FF on, beta=1', 'FF on, beta=0')
    choices = ((False, 1.), (True, 1.), (True, 0.))
    names = ('PI_150k_fallback', 'PI')
    rows, traces, convergence = [], {}, []
    for name in names:
        for label, (ff, beta) in zip(labels, choices):
            record = simulate(presets[name], model, ff, beta, model['timestep_s'])
            row = dict(controller=name, case=label, feedforward=ff, beta=beta,
                       **metrics(record),
                       step_10_to_15_mW=rising_edge_metrics(record, 250, 400),
                       restart_0_to_12_mW=rising_edge_metrics(record, 900, 1100))
            rows.append(row)
            traces[name, label] = record
            if beta == 0:
                fine = simulate(presets[name], model, ff, beta, model['timestep_s']/2)
                convergence.append(dict(controller=name,
                    rms_change_fraction=metrics(fine)['rms_all_mW']/row['rms_all_mW']-1,
                    waveform_rms_difference_mW=float(np.sqrt(np.mean(
                        (fine['power_mW'][::2]-record['power_mW'])**2)))))
            else:
                old = next(x for x in source['results'] if x['controller'] == name and
                           x['feedforward'] == ff and x['scale_error_fraction'] == 0 and
                           x['assumed_detector_noise_rms_mW'] == 0)
                assert abs(old['rms_all_mW']-row['rms_all_mW']) < 1e-10, 'Standard cases changed.'
            print(name, label, row['rms_all_mW'], row['step_10_to_15_mW'], flush=True)
    result = dict(model=model, equations={
        'command': 'u_virtual=FF*r+Kp*(beta*r-y)+I',
        'integral': 'dI/dt=Kp*omega_i*(r-y)',
        'reference_response': 'Y/R=P*(FF+beta*Kp+Ki/s)/(1+P*(Kp+Ki/s))',
        'disturbance_controller': 'Kp+Ki/s unchanged for every beta and FF setting'},
        results=rows, convergence=convergence,
        source_sha256={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                       for name in ('tracking_simulation.json','controller_starting_points.json')})
    (HERE/'setpoint_weighting_simulation.json').write_text(json.dumps(result, indent=2))
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    colors = ('#b24a35','#2166ac','#2a8c5a')
    for row_index, name in enumerate(names):
        visible_errors = []
        for label, color in zip(labels, colors):
            record = traces[name, label]
            t = record['time_s']*1e6
            style = '--' if label == labels[2] else '-'
            axes[row_index,0].plot(t, record['power_mW'], color=color, ls=style, label=label)
            axes[row_index,1].plot(t, record['power_mW'], color=color, ls=style)
            error = record['power_mW']-record['reference_mW']
            axes[row_index,2].plot(t, error, color=color, ls=style)
            visible_errors.append(error[(t >= 40) & (t <= 225)])
        axes[row_index,0].plot(t, record['reference_mW'], 'k--', lw=1)
        axes[row_index,1].plot(t, record['reference_mW'], 'k--', lw=1)
        axes[row_index,0].set(xlim=(247, 280 if row_index == 0 else 310),
                              ylim=(8.5,22), ylabel='Power [mW]', title='10→15 mW step')
        axes[row_index,1].set(xlim=(897,930 if row_index == 0 else 960),
                              ylim=(-.5,28), title='Restart from optical off to 12 mW')
        visible_errors = np.concatenate(visible_errors)
        span = max(.05, np.ptp(visible_errors))
        axes[row_index,2].set(xlim=(40,225),
                              ylim=(visible_errors.min()-.1*span, visible_errors.max()+.1*span),
                              ylabel='Power−desired [mW]', title='Same smooth ramps')
        axes[row_index,0].text(.03,.94,'PI 150 kHz' if row_index == 0 else 'PI 300 kHz',
                               transform=axes[row_index,0].transAxes, va='top')
        for ax in axes[row_index]:
            ax.set_xlabel('Time [µs]'); ax.grid(alpha=.25)
    axes[0,0].legend(fontsize=9,loc='lower right')
    fig.suptitle('Reference weighting changes the command kick; feedback disturbance dynamics stay fixed\n'
                 'Fitted delay/AOM model; no retrospective alignment; no hardware change')
    fig.savefig(HERE/'setpoint_weighting_simulation.png',dpi=170)
    plt.close(fig)
    lines = ['# PI feedforward and proportional setpoint weighting', '',
        'This is an offline comparison; no RTL, bitstream or board settings changed. It uses the same mixed shot, fitted AOM and readout-band plant as `tracking_simulation.py`, including 44.759 ns added processing. Each case begins at the same settled 8 mW. Zero target resets the integral; restart therefore tests a separate practical condition.', '',
        'The weighted controller is `u_virtual = FF*r + Kp*(beta*r-y) + I`, with `dI/dt = Ki*(r-y)` and `Ki=Kp*omega_i`. The integral always receives the full error. Consequently the disturbance-rejection denominator `1+P*(Kp+Ki/s)` is unchanged. The reference numerator becomes `P*(FF+beta*Kp+Ki/s)`.', '',
        '| Controller | Case | First 10–90% rise [µs] | Step overshoot [%] | ±2% settle [µs] | Whole mixed-shot RMS [mW] |',
        '|---|---|---:|---:|---:|---:|']
    for row in rows:
        edge=row['step_10_to_15_mW']
        settle=edge['settling_2_percent_us']
        lines.append(f"| {row['controller']} | {row['case']} | {edge['rise_10_to_90_us']:.3f} | {edge['overshoot_percent']:.1f} | {'not settled' if settle is None else f'{settle:.2f}'} | {row['rms_all_mW']:.5f} |")
    lines += ['', 'Feedforward gives a faster initial rise in this model. The worse overall error comes from the larger overshoot and ringing after arrival. Weighting the proportional reference reduces this kick, but does not eliminate it.', '',
        'Rise time uses the first threshold crossings and does not imply that the power stays at its target. Overshoot is a percentage of the 5 mW step, not of the final 15 mW power. Overshoot and settling are evaluated over the entire 150 µs plateau. RMS is calculated over the unchanged 1.1 ms physical timeline, including ramps, steps, off and restart. Actual modeled optical/readout power is scored; clipping and sensor-range validity remain in JSON.', '',
        'For a change of target Δr before the measured power has responded, the immediate virtual-command jump is `(FF+beta*Kp)*Δr`. Standard feedforward therefore adds to the proportional jump. Choosing beta=0 removes that proportional reference kick, but the integral continues charging while propagation delays the response. Approximately `Ki*Δr*delay` additional virtual power can accumulate during this interval, so beta=0 does not guarantee zero overshoot.', '',
        'With the 150 kHz preset, Kp≈0.353: the initial step coefficients are 0.353 (no FF), 1.353 (standard FF), and 1 (weighted FF). With the 300 kHz preset, Kp≈1.008, so no FF and weighted FF have almost the same linear reference response. Weighting can change which loop modes a pulse excites; it does not improve the stability margins of those modes.', '',
        'A slower desired waveform or a separate causal reference prefilter can limit excitation without reducing disturbance feedback gain. A model-following feedforward term would require a separately identified plant and an explicit choice of desired tracking dynamics; exact cancellation of an unknown pure delay cannot be causal. No such filter is implemented here.', '',
        'These are nominal-model predictions, not hardware validation. Sensor noise is omitted in this extra comparison; noise and ±5% scale tests for the original controller remain in `tracking_simulation.json`. The 300 kHz setting retains its very small gain margin. Only PI is tested here; extending weighting to PII/PIII requires preserving the full cascaded integral reference dynamics.', '',
        f"Both beta=0 cases were rerun at half timestep. Largest whole-shot RMS change: {100*max(abs(x['rms_change_fraction']) for x in convergence):.3f}%. The standard cases reproduce the preceding simulation's RMS to floating-point precision.", '',
        'Run `python setpoint_weighting_simulation.py` in this directory to regenerate JSON, figure and this note.']
    (HERE/'setpoint_weighting_simulation.md').write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    main()
