"""Analyze intensity-servo shots and recommend bounded, between-shot updates.

All powers use the same units (normally mW), with detector dark power removed.
A record contains time_s, reference_power, measured_power, actuator_codes and
optional boolean valid/clipped arrays. These functions never write hardware.

The incident-power estimate assumes P(t) = A * F(u(t-tau)), where F is the
measured relative AOM transmission on one monotonic branch. A is consequently
an effective power, including detector collection efficiency; an absolute
incident-power measurement needs an absolute efficiency calibration.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.signal import welch


def _arrays(record, minimum_samples=4):
    arrays = [np.asarray(record[key], dtype=float) for key in
              ('time_s', 'reference_power', 'measured_power', 'actuator_codes')]
    n = len(arrays[0])
    if n < minimum_samples or any(a.shape != (n,) or not np.isfinite(a).all() for a in arrays):
        raise ValueError(f'Provide at least {minimum_samples} finite samples of each shot signal.')
    dt_s = np.diff(arrays[0])
    if len(dt_s) and (np.any(dt_s <= 0) or not np.allclose(dt_s, dt_s.mean(), rtol=1e-5)):
        raise ValueError('Shot timestamps must be increasing and uniformly sampled.')
    return arrays


def save_record(path, record, metadata):
    """Save physical signals, calibration/controller settings and an exact shot key."""
    t, r, y, u = _arrays(record, minimum_samples=1)
    key = hashlib.sha256()
    key.update(np.asarray(t - t[0], dtype='<f8').tobytes())
    key.update(np.asarray(r, dtype='<f8').tobytes())
    for name in ('sensor_mode', 'power_units', 'sensor_calibration_sha256',
                 'aom_calibration_sha256', 'rf_chain'):
        key.update(json.dumps(metadata.get(name), sort_keys=True).encode())
    saved_metadata = dict(metadata, reference_key=key.hexdigest())
    payload = dict(record, metadata_json=json.dumps(saved_metadata, sort_keys=True))
    payload.setdefault('error_power', r-y)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # An explicit file handle preserves the exact requested filename.
    with path.open('wb') as stream:
        np.savez_compressed(stream, **payload)
    return saved_metadata


def shot_metrics(record, *, power_scale=None, ringing_band_hz=(5e4, 2e6),
                 startup_grace_s=10e-6, minimum_adc_counts=None,
                 maximum_excluded_startup_fraction=.001):
    """Tracking quality and a spectral ringing diagnostic, not a stability proof.

    A narrow peak may also be an externally driven disturbance. Only use a
    capture with adequate antialias filtering when interpreting this peak.
    After an observed zero-to-positive reference transition, the optical transit
    delay can leave the detector below its calibrated range briefly. With known
    minimum ADC counts, allow at most 10 us of below-range-only startup flags.
    Preserve the invalid samples and exclude their clamped powers from measured
    RMS/PSD. Reject a record if excluded startup exceeds the explicit fraction
    limit (default 0.1% of illuminated samples), rather than inventing power.
    With both ADC bounds known, the first in-range frame immediately after
    that startup may retain the interval-ORed range flag. Exclude that one
    ambiguous interval too; do not claim its intervening samples were valid.
    Above-range, persistent below-range and other faults remain disqualifying.
    The optimization score is ONLY the RMS calibrated optical tracking error
    in the record's power units (normally mW). Normalized RMS, ringing and
    overshoot are separate diagnostics, not weighted additions to that cost.
    """
    t, reference, measured, actuator = _arrays(record)
    valid = np.broadcast_to(np.asarray(record.get('valid', True), bool), t.shape)
    clipped = np.broadcast_to(np.asarray(record.get('clipped', False), bool), t.shape)
    complete = bool(record.get('complete', True))
    if power_scale is None:
        power_scale = np.max(np.abs(reference))
    if not np.isfinite(power_scale) or power_scale <= 0:
        raise ValueError('Use a positive power_scale in the same units as the record.')
    error = reference - measured
    illuminated = reference > 0
    if not illuminated.any():
        raise ValueError('No illuminated samples: dark response cannot use this calibrated optical-power score.')
    if not np.isfinite(startup_grace_s) or not 0 <= startup_grace_s <= 10e-6:
        raise ValueError('Startup grace must be between 0 and 10 us; it is only for the optical transit.')
    if (not np.isfinite(maximum_excluded_startup_fraction) or
            not 0 <= maximum_excluded_startup_fraction < 1):
        raise ValueError('Maximum excluded startup fraction must be between 0 (none) and 1 (exclusive).')
    dt_s = np.mean(np.diff(t))
    if minimum_adc_counts is None:
        minimum_adc_counts = record.get('sensor_adc_min_counts')
    excluded_startup = np.zeros(len(t), bool)
    startup_boundary = np.zeros(len(t), bool)
    if (startup_grace_s > 0 and minimum_adc_counts is not None and
            'raw_adc_counts' in record and 'sample_flags' in record):
        if not np.isfinite(minimum_adc_counts):
            raise ValueError('The measured ADC calibration minimum must be finite.')
        # Require a zero sample in THIS record before granting the grace: a
        # cropped trace starting at positive reference does not establish startup.
        rises = illuminated & np.r_[False, ~illuminated[:-1]]
        indices = np.arange(len(t))
        last_rise = np.maximum.accumulate(np.where(rises, indices, -len(t)))
        since_rise = (indices-last_rise)*dt_s
        raw_adc = np.asarray(record['raw_adc_counts'])
        below = raw_adc < float(minimum_adc_counts)
        only_range = np.asarray(record['sample_flags'], np.uint16) == 2
        startup_window = illuminated & (last_rise >= 0) & (since_rise < startup_grace_s)
        excluded_startup = startup_window & below & only_range & ~valid
        maximum_adc_counts = record.get('sensor_adc_max_counts')
        if maximum_adc_counts is not None:
            if not np.isfinite(maximum_adc_counts) or maximum_adc_counts <= minimum_adc_counts:
                raise ValueError('ADC calibration maximum must be finite and above its minimum.')
            in_range = (raw_adc >= minimum_adc_counts) & (raw_adc <= maximum_adc_counts)
            # The flags cover the whole decimation interval, whereas raw_adc
            # describes its final sample. Only the FIRST in-range frame after
            # each rise can inherit this bounded, explicitly ambiguous grace.
            candidates = np.flatnonzero(startup_window & in_range)
            _, first = np.unique(last_rise[candidates], return_index=True)
            first = candidates[first]
            startup_boundary[first] = (only_range[first] & ~valid[first] &
                                       np.r_[False, excluded_startup[:-1]][first])
            excluded_startup |= startup_boundary
    excluded_fraction = float(excluded_startup.sum()/illuminated.sum())
    startup_within_limits = excluded_fraction <= maximum_excluded_startup_fraction
    metric_samples = illuminated & valid
    if not metric_samples.any():
        return dict(usable=False, score=float('inf'),
                    reason='No calibrated illuminated samples remain after startup/fault exclusions.',
                    excluded_startup_s=float(excluded_startup.sum()*dt_s),
                    excluded_startup_fraction=excluded_fraction,
                    startup_within_limits=bool(startup_within_limits),
                    startup_boundary_samples=int(startup_boundary.sum()),
                    startup_ambiguous_s=float(startup_boundary.sum()*dt_s))
    fs_hz = 1 / dt_s
    # Use the longest illuminated segment for a uniformly sampled PSD. Joining
    # separated light pulses would create artificial phase/time discontinuities.
    boundaries = np.flatnonzero(np.diff(np.r_[False, metric_samples, False]))
    starts, ends = boundaries[::2], boundaries[1::2]
    longest = np.argmax(ends-starts)
    segment = error[starts[longest]:ends[longest]]
    f_hz, psd = welch(segment, fs=fs_hz, nperseg=min(16384, len(segment)))
    band = (f_hz >= ringing_band_hz[0]) & (f_hz <= ringing_band_hz[1])
    peak_hz = peak_to_floor = float('nan')
    if np.count_nonzero(band) >= 3 and np.max(psd[band]) > 0:
        indices = np.flatnonzero(band)
        peak_hz = float(f_hz[indices[np.argmax(psd[band])]])
        peak_to_floor = float(np.max(psd[band]) / max(np.median(psd[band]), 1e-300))
    rms = float(np.sqrt(np.mean(error[metric_samples]**2)))
    usable = (complete and (valid | excluded_startup).all() and not clipped.any()
              and startup_within_limits)
    return dict(error_rms_power=rms, error_rms_fraction=rms/power_scale,
                error_p99_power=float(np.quantile(np.abs(error[metric_samples]), .99)),
                overshoot_power=float(np.max((measured-reference)[metric_samples])),
                illuminated_fraction=float(illuminated.mean()),
                calibrated_illuminated_fraction=float(metric_samples.sum()/illuminated.sum()),
                excluded_startup_s=float(excluded_startup.sum()*dt_s),
                excluded_startup_fraction=excluded_fraction,
                startup_within_limits=bool(startup_within_limits),
                maximum_excluded_startup_fraction=float(maximum_excluded_startup_fraction),
                startup_boundary_samples=int(startup_boundary.sum()),
                startup_ambiguous_s=float(startup_boundary.sum()*dt_s),
                off_actuator_max_codes=float(np.max(actuator[~illuminated])) if (~illuminated).any() else None,
                actuator_min_codes=float(actuator.min()),
                actuator_max_codes=float(actuator.max()),
                valid_fraction=float(valid.mean()), clip_fraction=float(clipped.mean()),
                ringing_peak_hz=peak_hz, ringing_peak_to_floor=peak_to_floor,
                usable=bool(usable), score=rms if usable else float('inf'))


def next_controller_trial(baseline, bounds, trials, *, reference_key,
                          fraction=.1, repeats=3):
    """A small coordinate-search round around a known stable controller.

    trials: dictionaries with parameters, score, reference_key, and usable.
    Only trials with the same reference_key are compared. Each candidate gets
    `repeats` shots; parameters are changed by at most +/-fraction, one at a
    time. A zero-valued parameter stays zero (enable new poles deliberately).
    Bounds must come from the measured plant/stability analysis, not this
    function. This function returns recommendations; it does not run a shot.
    Candidate cost is the root mean square of repeated shots' RMS tracking
    errors, still in power units. Scatter is reported separately, not added.

    Once complete, adopt best_parameters and begin a new round with a smaller
    fraction if necessary. Keep controller order, sensor mode, feedforward and
    power adaptation fixed during a round to avoid confounded comparisons.
    """
    if not 0 < fraction <= .25 or not isinstance(repeats, int) or repeats < 2:
        raise ValueError('Use 0 < fraction <= 0.25 and at least two repeats.')
    baseline = {name: float(value) for name, value in baseline.items()}
    for name, value in baseline.items():
        lower, upper = bounds[name]
        if not np.isfinite([value, lower, upper]).all() or not lower <= value <= upper:
            raise ValueError(f'Baseline {name} is outside its finite bounds.')
    candidates = [baseline]
    for name, value in baseline.items():
        if value == 0:
            continue
        for factor in (1-fraction, 1+fraction):
            candidate = dict(baseline)
            candidate[name] = float(np.clip(value*factor, *bounds[name]))
            if candidate not in candidates:
                candidates.append(candidate)
    summary = []
    for candidate in candidates:
        matching = [trial for trial in trials
                    if trial.get('reference_key') == reference_key
                    and trial.get('parameters') == candidate]
        # Any faulty candidate is abandoned for this round, not repeatedly
        # retried until a lucky shot hides a stability problem.
        failed = any(not p.get('usable', False) or not np.isfinite(p['score'])
                     for p in matching)
        if failed:
            summary.append(dict(parameters=candidate, score=float('inf'), shots=len(matching)))
            if candidate == baseline:
                return dict(action='stop', reason='Baseline shot was invalid or clipped.')
            continue
        if len(matching) < repeats:
            return dict(action='measure', parameters=candidate,
                        repeat_index=len(matching), candidates=candidates)
        scores = np.asarray([p['score'] for p in matching], float)
        median = float(np.median(scores))
        scatter = float(1.4826*np.median(np.abs(scores-median)))
        summary.append(dict(parameters=candidate, score=float(np.sqrt(np.mean(scores**2))),
                            median_score=median, scatter=scatter, shots=len(matching)))
    best = min(summary, key=lambda item: item['score'])
    return dict(action='complete', best_parameters=best['parameters'], summary=summary)


def incident_power_observation(record, aom_table, *, minimum_transmission=.03,
                               block_s=.001, settle_s=.0001,
                               delay_s=0., maximum_error_fraction=.03,
                               observation_floor_fraction=.01):
    """Estimate effective incident power from settled, valid parts of a shot.

    aom_table contains u_codes and F_relative. Pointwise P/F(u) is only used
    after an unchanged reference has settled; it is invalid during rapid
    transients. `block_s` must exceed the residual noise correlation time.
    The uncertainty floor prevents millions of correlated ADC samples from
    being mistaken for millions of independent optical power measurements.
    At least three complete stationary blocks are required.
    """
    t, reference, measured, actuator = _arrays(record)
    u = np.asarray(aom_table['u_codes'], float)
    transmission = np.asarray(aom_table['F_relative'], float)
    if (u.ndim != 1 or u.shape != transmission.shape or len(u) < 3 or
            not np.isfinite(u+transmission).all() or np.any(np.diff(u) <= 0) or
            np.any(transmission <= 0)):
        raise ValueError('AOM table needs increasing commands and positive transmission.')
    if (block_s <= 0 or settle_s < 0 or delay_s < 0 or
            observation_floor_fraction <= 0 or maximum_error_fraction <= 0):
        raise ValueError('Use positive block time/error bounds and nonnegative delays.')
    dt_s = np.mean(np.diff(t))
    delayed_command = np.interp(t-delay_s, t, actuator)
    in_table = (delayed_command >= u[0]) & (delayed_command <= u[-1])
    f = np.interp(delayed_command, u, transmission)
    valid = np.broadcast_to(np.asarray(record.get('valid', True), bool), t.shape)
    clipped = np.broadcast_to(np.asarray(record.get('clipped', False), bool), t.shape)
    # Tiny count changes are still changes: do not estimate power from ramps.
    changes = np.r_[True, np.diff(reference) != 0]
    last_change = np.maximum.accumulate(np.where(changes, np.arange(len(t)), 0))
    settled = (np.arange(len(t))-last_change)*dt_s >= settle_s
    good = (valid & ~clipped & in_table & settled & (t >= t[0]+delay_s) &
            (f >= minimum_transmission) & (measured > 0) & (reference > 0) &
            (np.abs(measured-reference) <= maximum_error_fraction*reference))
    block_n = max(1, int(np.ceil(block_s/dt_s)))
    block_log_power = []
    for start in range(0, len(t)-block_n+1, block_n):
        end = start+block_n
        if good[start:end].all():
            block_log_power.append(float(np.mean(np.log(measured[start:end]/f[start:end]))))
    if not record.get('complete', True) or len(block_log_power) < 3:
        return dict(valid=False, blocks=len(block_log_power),
                    reason='Need >=3 complete, settled, unclipped blocks in the calibrated range.')
    values = np.asarray(block_log_power)
    center = float(np.median(values))
    # Use block scatter (not scatter/sqrt(N)) conservatively: drift and residual
    # calibration error usually dominate photon noise in this application.
    scatter = float(1.4826*np.median(np.abs(values-center)))
    variance = max(scatter**2, observation_floor_fraction**2)
    return dict(valid=True, blocks=len(values), log_power=center,
                log_variance=variance,
                systematic_log_variance=float(observation_floor_fraction**2),
                power=float(np.exp(center)))


def power_prior(power, fractional_uncertainty=.1):
    """Initialize the scalar Gaussian prior for log(effective incident power)."""
    if not np.isfinite([power, fractional_uncertainty]).all() or power <= 0 or fractional_uncertainty <= 0:
        raise ValueError('Use a positive finite power and fractional uncertainty.')
    return dict(log_power=float(np.log(power)), log_variance=float(fractional_uncertainty**2))


def update_power_estimate(prior, observation, *, elapsed_s,
                          drift_fraction_per_sqrt_s=.01, maximum_innovation_sigma=5.):
    """Scalar Kalman/Bayesian update in log power with a random-walk drift prior.

    Reject unexplained large changes, rather than silently applying a large
    controller-gain change after a detector fault or calibration-mode switch.
    Reinitialize deliberately after changing detector attenuation/calibration.
    """
    if elapsed_s < 0 or drift_fraction_per_sqrt_s < 0 or maximum_innovation_sigma <= 0:
        raise ValueError('Invalid prediction interval, drift, or rejection threshold.')
    mean = float(prior['log_power'])
    # The AOM/sensor model uncertainty is shared by every shot. Unlike random
    # noise, it cannot be averaged down by repeating the same observation.
    systematic = max(float(prior.get('systematic_log_variance', 0.)),
                     float(observation.get('systematic_log_variance', 0.)))
    if not np.isfinite(systematic) or systematic < 0:
        raise ValueError('Systematic log variance must be finite and nonnegative.')
    variance = max(float(prior['log_variance']), systematic) + elapsed_s*drift_fraction_per_sqrt_s**2
    result = dict(log_power=mean, log_variance=variance,
                  systematic_log_variance=systematic, updated=False)
    if observation.get('valid', False):
        noise = float(observation['log_variance'])
        innovation = float(observation['log_power'])-mean
        if not np.isfinite([mean, variance, noise, innovation]).all() or variance <= 0 or noise <= 0:
            raise ValueError('Prior and observation variances must be finite and positive.')
        result['innovation_sigma'] = innovation/np.sqrt(variance+noise)
        if abs(result['innovation_sigma']) <= maximum_innovation_sigma:
            gain = variance/(variance+noise)
            result.update(log_power=mean+gain*innovation,
                          log_variance=max((1-gain)*variance, systematic), updated=True)
    result['power'] = float(np.exp(result['log_power']))
    result['fractional_uncertainty'] = float(np.sqrt(result['log_variance']))
    return result


def gain_scale_recommendation(estimate, nominal_power, *, previous_scale=1.,
                              maximum_step_fraction=.05, limits=(.5, 2.)):
    """Bound 1/A gain scaling between shots, relative to a known operating point.

    Apply this ONCE: when the output inverse already scales (feedforward +
    feedback) by 1/A, leave controller coefficients unchanged. Otherwise both
    virtual-transmission feedforward and controller output need this factor.
    This helper does not load a table, change gains, or transfer integrator state.
    """
    if (nominal_power <= 0 or previous_scale <= 0 or
            not 0 < maximum_step_fraction <= .25 or not 0 < limits[0] <= limits[1]):
        raise ValueError('Use positive powers/scales and a <=25% between-shot step.')
    if not estimate.get('updated', False):
        return dict(scale=float(previous_scale), changed=False, reason='No accepted power update.')
    target = nominal_power / float(np.exp(estimate['log_power']))
    lower = max(limits[0], previous_scale*(1-maximum_step_fraction))
    upper = min(limits[1], previous_scale*(1+maximum_step_fraction))
    if lower > upper:
        raise ValueError('Previous gain scale lies outside the allowed range.')
    value = float(np.clip(target, lower, upper))
    return dict(scale=value, changed=value != previous_scale, target_scale=target,
                limited=value != target)
