"""Known physical gain/delay, coherent-sum units, calibration leakage and cleanup."""
import cmath
import tempfile
import unittest
import sys
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path
from unittest.mock import patch

import test_laser_pll_loop_sweep as fixture_fra
import laser_pll_loopback as lb
import numpy as np


class Loopback(unittest.TestCase):
    def setUp(self):
        fixture = fixture_fra.Analyzer(); fixture.setUp(); self.ol = fixture.ol
        ol = self.ol
        ol.pll_acquisition_status.values[0] = 5|128
        ol.pll_acquisition.values[8] = 2048
        ol._laser_pll_loopback_setup = dict(output_limits=None, receiver_settings={'fixed':True})
        ol.pll_loopback_i, ol.pll_loopback_q = fixture_fra.GPIO(), fixture_fra.GPIO()
        self.gi, self.gq, self.delay_s = -.3, .7, 403e-9
        self.fault = 0
        def write(offset, value):
            ol.pll_fra.values[offset] = value
            ol.pll_fra.values[8] = 4 | self.fault if value else 0
            if not value: return
            assert value == 3
            n = ol.pll_fra_window.read(8)
            ol.pll_fra_samples.values[8] = n
            amplitude = ol.pll_fra_tone.read(0x18)
            if amplitude & 1<<19: amplitude -= 1<<20
            f = ol.pll_fra_tone.read(0x10)*8*lb.FS_HZ/2**32
            h = cmath.exp(-2j*np.pi*f*self.delay_s)
            for ip,g in [(ol.pll_fra_error,self.gi),(ol.pll_fra_drive,self.gq)]:
                z = amplitude*g*h
                ip.values.update({0x10:1,0x2c:1,0x4c:1})
                for address,v in [(0x20,z.real),(0x40,z.imag)]:
                    raw = round(v*n*32768*4/2)&((1<<72)-1)
                    for k in range(3): ip.values[address+4*k] = raw >> (32*k) & 0xffffffff
            bias = ol.pll_acquisition.read(8) & 65535
            if bias & 32768: bias -= 65536
            for ip,g,leakage in [(ol.pll_loopback_i,self.gi,200),(ol.pll_loopback_q,self.gq,-333)]:
                raw = round((bias*g+leakage)*n*4)&((1<<64)-1)
                ip.values = {0:raw&0xffffffff,8:raw>>32}
        ol.pll_fra.write = write
        self.settings = patch.object(lb,'receiver_settings',return_value={'fixed':True})
        self.settings.start()
        self.sleep = patch.object(lb.time,'sleep',lambda _:None); self.sleep.start()
        self.addCleanup(self.settings.stop); self.addCleanup(self.sleep.stop)

    def test_setup_same_beat_pair_and_preserves_other_converters(self):
        ol = self.ol
        adc = SimpleNamespace(MixerSettings={'Freq':0.0})
        tp = SimpleNamespace(MixerSettings={'Freq':90.0})
        dac = SimpleNamespace(MixerSettings={'Freq':0.0}, ResetNCOPhase=Mock(), UpdateEvent=Mock())
        ol.usp_rf_data_converter_0 = SimpleNamespace(adc_tiles=[SimpleNamespace(blocks=[None,None,None,adc])],
            dac_tiles=[SimpleNamespace(blocks=[None,tp]),SimpleNamespace(blocks=[None,dac])])
        ol.ip_dict = {'usp_rf_data_converter_0':{'parameters':{'ADC_Decimation_Mode03':'1',
                        'ADC_Data_Type03':'0','DAC_Interpolation_Mode11':'4'}}}
        constants = SimpleNamespace(EVNT_SRC_IMMEDIATE=0,MIXER_TYPE_FINE=2,MIXER_MODE_C2R=2,
                                    MIXER_SCALE_1P0=1,EVENT_MIXER=1)
        with patch.dict(sys.modules, xrfdc=constants), patch.object(lb.laser_pll,'set_reference_frequency') as ref:
            for mode, frequency in [('rf',90.0),('mixer',0.0)]:
                self.settings.return_value = None
                with patch.object(lb,'receiver_settings',return_value={'tp_lo_mixer':{'Freq':90.0},
                                                                     'tp_lo_amplitude_codes':8191}):
                    lb.setup(ol,mode=mode,output_limits=lb.voltage_limits(.002,.012))
                self.assertEqual(dac.MixerSettings['Freq'],frequency)
                ref.assert_called_with(ol,90e6,restart_phase=True)
        self.assertEqual(adc.MixerSettings,{'Freq':0.0})
        self.assertEqual(tp.MixerSettings,{'Freq':90.0})

    def test_measured_units_both_signs_and_dc(self):
        for polarity in (1,-1):
            point = lb.measure_point(self.ol,1e6,polarity=polarity)
            h = cmath.exp(-2j*np.pi*point['frequency_hz']*self.delay_s)
            self.assertAlmostEqual(point['i'],32*self.gi*h)
            self.assertAlmostEqual(point['q'],32*self.gq*h)
            self.assertAlmostEqual(point['mean_i'],2048*self.gi+200)
            self.assertEqual(self.ol.pll_fra.read(0),0)
            self.assertEqual(self.ol.pll_fra_tone.read(0x18),0)

    def test_dc_calibration_removes_leakage(self):
        cal = lb.calibrate(self.ol)
        self.assertAlmostEqual(cal['gain_i'],self.gi)
        self.assertAlmostEqual(cal['gain_q'],self.gq)
        self.assertEqual(self.ol.pll_acquisition.read(8),2048)
        p = lb.measure_point(self.ol,1e6)
        h,cross = lb.project(p,cal)
        self.assertAlmostEqual(h,cmath.exp(-2j*np.pi*p['frequency_hz']*self.delay_s))
        self.assertAlmostEqual(cross,0)

    def test_sweep_saved_and_delay_recovered(self):
        cal = lb.calibrate(self.ol)
        with tempfile.TemporaryDirectory() as work:
            path = Path(work)/'loop.csv'
            rows = lb.sweep(self.ol,np.geomspace(10000,1e6,20),cal,repeats=2,max_repeats=2,csv_path=path)
            result = lb.fit_delay(rows)
            self.assertAlmostEqual(result['delay_s'],self.delay_s,places=14)
            self.assertEqual(len(path.read_text().splitlines()),21)
            self.assertEqual(len(path.with_name('loop_blocks.csv').read_text().splitlines()),41)

    def test_fault_cleanup_and_preflight(self):
        for bit in range(3,8):
            self.fault = 1<<bit
            with self.assertRaisesRegex(RuntimeError,'Invalid loopback'): lb.measure_point(self.ol,1000)
            self.assertEqual(self.ol.pll_fra_tone.read(0x18),0)
        self.ol.pll_acquisition_status.values[0] = 3|128
        before = list(self.ol.pll_acquisition.writes)
        with self.assertRaises(ValueError): lb.calibrate(self.ol)
        self.assertEqual(self.ol.pll_acquisition.writes,before)

    def test_window_keeps_mhz_probe_and_long_integration(self):
        for frequency in [10,1234,1e6,5e6]:
            p = lb.frequency_plan(frequency)
            self.assertGreaterEqual(p['integration_s'],1-.5/lb.FS_HZ)
            self.assertLessEqual(abs(p['frequency_hz']-frequency),.229)
            cycles = p['measure_clocks']*p['frequency_hz']/lb.FS_HZ
            self.assertLessEqual(abs(cycles-round(cycles)),p['frequency_hz']/lb.FS_HZ)

    def test_old_sweep_dependency_rejected_before_output_writes(self):
        old_fra = SimpleNamespace(__file__='/old/laser_pll_loop_sweep.py')
        with patch.object(lb,'fra',old_fra):
            for call in (lambda: lb.setup(self.ol,mode='rf'),
                         lambda: lb.calibrate(self.ol),
                         lambda: lb.measure_point(self.ol,1000)):
                with self.assertRaisesRegex(RuntimeError,'Stale or mismatched'):
                    call()
        for ip in (self.ol.pll_acquisition,self.ol.pll_control,self.ol.pll_fra_tone):
            self.assertEqual(ip.writes,[])

    def test_voltage_limits_both_polarities_and_calibration(self):
        # Example bench response: 10 mV offset, +/-0.2 mV/code.
        ol = self.ol
        for sign in (-1,1):
            limits = lb.voltage_limits(.010,.010+sign*.020)
            ol._laser_pll_loopback_setup['output_limits'] = limits
            ol.pll_acquisition.values[8] = 0
            cal = lb.calibrate(ol)
            self.assertAlmostEqual(cal['gain_i'],self.gi)
            self.assertAlmostEqual(cal['gain_q'],self.gq)
            p = lb.measure_point(ol,1000)
            self.assertAlmostEqual(p['predicted_peak_V'],.0164)
            self.assertEqual(ol.pll_acquisition.read(8),0)
            before = list(ol.pll_acquisition.writes), list(ol.pll_fra_tone.writes)
            # Previously suggested +/-512 codes reaches >100 mV even at zero bias.
            with self.assertRaisesRegex(ValueError,'D2S output'):
                lb.calibrate(ol,step_codes=512)
            with self.assertRaisesRegex(ValueError,'D2S output'):
                lb.measure_point(ol,1000,amplitude_codes=512)
            self.assertEqual(before,(ol.pll_acquisition.writes,ol.pll_fra_tone.writes))

    def test_setup_requires_voltage_bound_and_checks_bias_before_writes(self):
        for kwargs in (dict(),dict(output_limits=lb.voltage_limits(.010,.030),bias_codes=2048)):
            with self.assertRaises(ValueError): lb.setup(self.ol,mode='mixer',**kwargs)
        self.assertEqual(self.ol.pll_control.writes,[])
        self.assertEqual(self.ol.pll_acquisition.writes,[])
        for zero,test in ((float('nan'),.01),(.01,.01),(.090,.095)):
            with self.assertRaises(ValueError): lb.voltage_limits(zero,test)

    def test_guard_lost_setup_changed_config_and_busy_calibration(self):
        del self.ol._laser_pll_loopback_setup
        with self.assertRaisesRegex(ValueError,'setup'): lb.measure_point(self.ol,1000)
        self.ol._laser_pll_loopback_setup = dict(output_limits=None,receiver_settings={'changed':True})
        with self.assertRaisesRegex(ValueError,'settings changed'): lb.calibrate(self.ol)
        self.ol._laser_pll_loopback_setup['receiver_settings'] = {'fixed':True}
        self.ol.pll_fra.values[0] = 1
        with self.assertRaisesRegex(ValueError,'Stop the previous'): lb.calibrate(self.ol)
        self.assertEqual(self.ol.pll_acquisition.writes,[])


if __name__ == '__main__': unittest.main()
