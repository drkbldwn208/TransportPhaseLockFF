"""Physical checks for shot scoring, bounded optimization and optical drift inference."""
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python_scripts'))
import intensity_shot_analysis as shots


def synthetic(incident_power=10., transmission=.3, noise=.001):
    rng = np.random.default_rng(27)
    fs_hz = 2e6
    time_s = np.arange(40000)/fs_hz
    command = float(np.arcsin(np.sqrt(transmission))/1e-4)
    measured = incident_power*transmission*(1+noise*rng.normal(size=len(time_s)))
    record = dict(time_s=time_s, reference_power=np.full(len(time_s), incident_power*transmission),
                  measured_power=measured, actuator_codes=np.full(len(time_s), command),
                  valid=True, clipped=False, complete=True)
    u = np.linspace(500, 15000, 4096)
    table = dict(u_codes=u, F_relative=np.sin(u*1e-4)**2)
    return record, table


class ShotAnalysis(unittest.TestCase):
    def test_observation_measures_input_power_not_output_power(self):
        # Feedback holds different optical powers by using different commands;
        # P/F(u) must recover the common illumination, not its output setpoint.
        for transmission in (.1, .3, .7):
            record, table = synthetic(incident_power=12., transmission=transmission)
            result = shots.incident_power_observation(record, table)
            self.assertTrue(result['valid'])
            self.assertAlmostEqual(result['power'], 12., delta=.005)
            self.assertGreaterEqual(result['log_variance'], .01**2)

    def test_ramp_and_clipping_cannot_update_power(self):
        record, table = synthetic()
        record['reference_power'] += np.arange(len(record['time_s']))*1e-6
        self.assertFalse(shots.incident_power_observation(record, table)['valid'])
        record, table = synthetic()
        record['clipped'] = True
        self.assertFalse(shots.incident_power_observation(record, table)['valid'])
        self.assertFalse(shots.shot_metrics(record)['usable'])

    def test_actuator_calibration_is_not_extrapolated(self):
        record, table = synthetic()
        record['actuator_codes'][:] = 20000
        self.assertFalse(shots.incident_power_observation(record, table)['valid'])

    def test_bayesian_estimator_tracks_drift_and_rejects_blip(self):
        state = shots.power_prior(10., .1)
        for incident in np.linspace(10., 11., 20):
            record, table = synthetic(incident_power=incident)
            observation = shots.incident_power_observation(record, table)
            state = shots.update_power_estimate(state, observation, elapsed_s=1)
        self.assertAlmostEqual(state['power'], 11., delta=.1)
        observation.update(log_power=np.log(1.), power=1.)
        bad = shots.update_power_estimate(state, observation, elapsed_s=1)
        self.assertFalse(bad['updated'])
        self.assertEqual(bad['log_power'], state['log_power'])
        self.assertGreater(bad['log_variance'], state['log_variance'])

    def test_inverse_power_gain_scaling_is_bounded(self):
        state = dict(log_power=np.log(20.), updated=True)
        result = shots.gain_scale_recommendation(state, 10.)
        self.assertAlmostEqual(result['target_scale'], .5)
        self.assertEqual(result['scale'], .95)
        self.assertTrue(result['limited'])
        state['updated'] = False
        self.assertEqual(shots.gain_scale_recommendation(state, 10.)['scale'], 1.)

    def test_repeated_shots_do_not_average_away_calibration_uncertainty(self):
        record, table = synthetic()
        observation = shots.incident_power_observation(record, table, observation_floor_fraction=.01)
        state = shots.power_prior(10.)
        for _ in range(1000):
            state = shots.update_power_estimate(state, observation, elapsed_s=1.,
                                               drift_fraction_per_sqrt_s=0.)
        self.assertGreaterEqual(state['fractional_uncertainty'], .01)
        self.assertEqual(state['systematic_log_variance'], .01**2)

    def test_optimizer_needs_repeats_and_never_accepts_faulty_candidate(self):
        baseline = dict(kp=1., ki=2.)
        bounds = dict(kp=(.8, 1.2), ki=(1.5, 2.5))
        trials = []
        for _ in range(30):
            result = shots.next_controller_trial(baseline, bounds, trials,
                                                  reference_key='same-shot', repeats=2)
            if result['action'] == 'complete':
                break
            parameters = result['parameters']
            bad = parameters['ki'] > 2.
            score = (parameters['kp']-.9)**2 + .1
            trials.append(dict(parameters=parameters, reference_key='same-shot',
                               score=score, usable=not bad))
        self.assertEqual(result['action'], 'complete')
        self.assertEqual(result['best_parameters'], dict(kp=.9, ki=2.))
        first = shots.next_controller_trial(baseline, bounds, trials,
                                             reference_key='different-shot', repeats=2)
        self.assertEqual(first['parameters'], baseline)
        self.assertEqual(first['repeat_index'], 0)

    def test_ring_frequency_and_record_roundtrip(self):
        record, _ = synthetic(noise=.00001)
        record['measured_power'] += .1*np.sin(2*np.pi*175e3*record['time_s'])
        result = shots.shot_metrics(record)
        self.assertAlmostEqual(result['ringing_peak_hz'], 175e3, delta=200.)
        self.assertGreater(result['ringing_peak_to_floor'], 1e3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'shot.npz'
            metadata = shots.save_record(path, record, dict(sensor_mode='low', power_units='mW'))
            with np.load(path, allow_pickle=False) as saved:
                np.testing.assert_allclose(saved['error_power'], record['reference_power']-record['measured_power'])
            self.assertEqual(len(metadata['reference_key']), 64)

    def test_dark_start_grace_preserves_unknown_power_and_rejects_persistent_faults(self):
        fs_hz = 2e6
        time_s = np.arange(200000)/fs_hz  #100ms experimental shot
        illuminated = time_s >= .001
        startup = illuminated & (time_s < .001003)  #3us optical transient
        reference = illuminated.astype(float)*10.
        flags = np.where(~illuminated | startup, 2, 0).astype(np.uint16)
        raw_adc = np.where(~illuminated | startup, 0, 1000)
        record = dict(time_s=time_s,reference_power=reference,
                      measured_power=np.where(~illuminated | startup, .1, 10.),
                      actuator_codes=illuminated.astype(float)*5000,
                      valid=~startup,clipped=False,complete=True,
                      sample_flags=flags,raw_adc_counts=raw_adc,sensor_adc_min_counts=20)
        result = shots.shot_metrics(record)
        self.assertTrue(result['usable'])
        self.assertAlmostEqual(result['excluded_startup_s'], 3e-6, delta=1e-12)
        self.assertEqual(result['error_rms_power'], 0.)
        self.assertEqual(result['score'], result['error_rms_power'])
        self.assertFalse(shots.shot_metrics(record, maximum_excluded_startup_fraction=1e-6)['usable'])
        self.assertTrue((record['valid'][startup]==False).all()) #flags/data unchanged

        # With no calibration bound there is no blind grace for range flags.
        del record['sensor_adc_min_counts']
        self.assertFalse(shots.shot_metrics(record)['usable'])
        record['sensor_adc_min_counts'] = 20

        # Above-range startup is never excused.
        record['raw_adc_counts'][startup] = 30000
        self.assertFalse(shots.shot_metrics(record)['usable'])
        record['raw_adc_counts'][startup] = 0

        # Persisting below range for 20 us exceeds the explicit 10 us maximum.
        persistent = illuminated & (time_s < .001020)
        record['sample_flags'][persistent] = 2
        record['raw_adc_counts'][persistent] = 0
        record['valid'][persistent] = False
        self.assertFalse(shots.shot_metrics(record)['usable'])

    def test_startup_interval_ored_flags_allow_one_ambiguous_boundary_only(self):
        # At D=6 one stored raw sample covers 64 fabric clocks. The first
        # in-range sample can retain a flag from the below-range part of that
        # interval; a second flagged in-range frame is not startup carryover.
        fs_hz = 245.76e6 / 64
        n = 384000
        reference = np.full(n, 10.)
        reference[:4] = 0.
        below = np.arange(n) < 10
        flags = np.where(np.arange(n) <= 10, 2, 0).astype(np.uint16)
        valid = (flags == 0) | (reference == 0)
        record = dict(time_s=np.arange(n)/fs_hz, reference_power=reference,
                      measured_power=np.where(below, .1, 10.),
                      actuator_codes=np.where(reference > 0, 5000., 0.),
                      valid=valid, clipped=False, complete=True,
                      sample_flags=flags, raw_adc_counts=np.where(below, 0, 1000),
                      sensor_adc_min_counts=20, sensor_adc_max_counts=2000)
        result = shots.shot_metrics(record)
        self.assertTrue(result['usable'])
        self.assertEqual(result['startup_boundary_samples'], 1)
        self.assertAlmostEqual(result['startup_ambiguous_s'], 1/fs_hz)
        self.assertAlmostEqual(result['excluded_startup_s'], 7/fs_hz)
        self.assertEqual(result['error_rms_power'], 0.)
        self.assertEqual(result['score'], result['error_rms_power'])
        self.assertFalse(record['valid'][10])  # preserved, never valid for P/F(u)

        record['sample_flags'][11] = 2
        record['valid'][11] = False
        self.assertFalse(shots.shot_metrics(record)['usable'])
        record['sample_flags'][11] = 0
        record['valid'][11] = True
        record['raw_adc_counts'][10] = 3000  # current sample above upper bound
        self.assertFalse(shots.shot_metrics(record)['usable'])
        record['raw_adc_counts'][10] = 1000
        del record['sensor_adc_max_counts']
        self.assertFalse(shots.shot_metrics(record)['usable'])

    def test_cost_is_physical_rms_without_auxiliary_weights(self):
        record, _ = synthetic(noise=0.)
        record['measured_power'] += .25
        result = shots.shot_metrics(record, power_scale=1e6)
        self.assertAlmostEqual(result['score'], .25)
        self.assertAlmostEqual(result['error_rms_power'], .25)
        self.assertAlmostEqual(result['overshoot_power'], .25)
        # The normalization diagnostic and overshoot do not alter RMS cost.
        self.assertAlmostEqual(result['error_rms_fraction'], .25/1e6)

        baseline = dict(kp=1.)
        trials = [dict(parameters=baseline, reference_key='same', score=value, usable=True)
                  for value in (1., 3.)]
        result = shots.next_controller_trial(baseline, dict(kp=(1.,1.)), trials,
                                             reference_key='same', repeats=2)
        self.assertEqual(result['action'], 'complete')
        self.assertAlmostEqual(result['summary'][0]['score'], np.sqrt(5.))
        self.assertGreater(result['summary'][0]['scatter'], 0.)


if __name__ == '__main__':
    unittest.main()
