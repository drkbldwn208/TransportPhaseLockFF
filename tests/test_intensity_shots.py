"""Host-side shot capture planning, exact packing and safe receive lifecycle."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from copy import deepcopy
import json

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python_scripts'))
import intensity_shots as shots
import intensity_shot_analysis as analysis
from tp_intensity_rfsoc_buffer import TpIntensityBufferController


class Buffer(np.ndarray):
    def __new__(cls, shape, dtype):
        obj = np.zeros(shape, dtype).view(cls)
        obj.freed = False
        return obj

    def freebuffer(self):
        self.freed = True

    def flush(self):
        pass


def mock_overlay():
    events = []
    control_words = {0: 0, 8: 0}
    tail_words = {0: 0, 8: shots.FEATURE_VERSION}
    def control_write(address, value):
        control_words[address] = value
        events.append(('control', address, value))
    control = SimpleNamespace(read=lambda a: control_words[a], write=control_write)
    tail = SimpleNamespace(read=lambda a: tail_words[a], write=lambda a,v: tail_words.update({a:v}))
    receive = SimpleNamespace(running=True, idle=False, transferred=0)
    receive.transfer = lambda buffer: events.append(('receive_armed',))
    receive.wait = lambda: events.append(('receive_wait',))
    receive.stop = lambda: events.append(('receive_stop',))
    receive.start = lambda: events.append(('receive_start',))
    dma = SimpleNamespace(recvchannel=receive, mmio=SimpleNamespace(read=lambda a: 0))
    overlay = SimpleNamespace(intensity_shot_control=control, intensity_shot_tail=tail,
                              intensity_shot_dma=dma,
                              ip_dict={k: {} for k in ('intensity_shot_control', 'intensity_shot_tail', 'intensity_shot_dma')})
    return overlay, control_words, events


class Shots(unittest.TestCase):
    def test_existing_buffer_arms_receive_before_command_and_saves_on_completion(self):
        ol, registers, events = mock_overlay()
        sender = SimpleNamespace(running=False, idle=True)
        def start():
            sender.running = True
            events.append(('command_start',))
        def stop():
            sender.running = False
            sender.idle = True
            events.append(('command_stop',))
        def transfer(buffer):
            self.assertTrue(sender.running)
            sender.idle = False
            events.append(('command_transfer',))
        sender.start, sender.stop, sender.transfer = start, stop, transfer
        ol.axi_dma_6 = SimpleNamespace(sendchannel=sender)
        ol.axi_gpio_11 = SimpleNamespace(channel1=SimpleNamespace(write=lambda *a,**k:None))
        servo = SimpleNamespace(configuration=lambda ol:{'power_per_code':.01,'power_units':'mW',
            'control_word':1, 'sensor_power_limits_mW':{'low_power':[1.,15.]},
            'effective_power_mW':20., 'maximum_transmission_fraction':.5,
            'sensor_calibration_sha256':'test-sensor', 'aom_calibration_sha256':'test-aom'})
        calibration = SimpleNamespace(configuration=lambda ol:{'linearized_servo':servo.configuration(ol)})
        def finish(overlay, armed, **kwargs):
            sender.idle = True
            events.append(('shot_saved',))
            return dict(path='/tmp/example.npz', complete=True, samples=10)
        with patch.dict(sys.modules, {'pynq':SimpleNamespace(allocate=Buffer),'intensity_servo':servo,
                                      'intensity_calibration':calibration}), \
                patch.object(shots,'finish',side_effect=finish):
            controller = TpIntensityBufferController(overlay=ol,max_words=16,
                shot_recording={'directory':'/tmp/shot-test'})
            controller.load_and_arm(np.array([(1000<<16)|24575,0],np.uint32))
            names = [e[0] for e in events]
            self.assertLess(names.index('receive_armed'),names.index('command_transfer'))
            self.assertTrue(controller.status()['shot_capture_armed'])
            result = controller.wait_done()
            self.assertTrue(result['shot_record']['complete'])
            self.assertFalse(controller.status()['shot_capture_armed'])
            with self.assertRaisesRegex(ValueError, 'Shot reference'):
                controller.load_and_arm(np.array([(2000<<16)|24575,0],np.uint32))
            self.assertFalse(controller.status()['shot_capture_armed'])
            ol.ip_dict['intensity_control'] = {}
            ol.intensity_control = SimpleNamespace(read=lambda a:1)
            with self.assertRaisesRegex(RuntimeError, 'FRA'):
                controller.load_and_arm(np.array([(1000<<16)|24575,0],np.uint32))

    def test_hundred_ms_memory_and_no_silent_rate_change(self):
        plan = shots.capture_plan(.1)
        self.assertEqual(plan['sample_rate_hz'], 3.84e6)
        self.assertLess(plan['buffer_bytes'], 6.3e6)
        with self.assertRaises(ValueError):
            shots.capture_plan(2.)
        ol, _, _ = mock_overlay()
        with self.assertRaisesRegex(ValueError, 'byte-length'):
            shots.arm(ol, maximum_samples=4194304)
        ol.intensity_shot_dma.recvchannel._max_size = 4095
        with self.assertRaisesRegex(ValueError, 'byte-length'):
            shots.arm(ol, maximum_samples=256)
        duration = (4194304-16)/(shots.FS_HZ/64)
        with self.assertRaises(ValueError):
            shots.capture_plan(duration, decimation_log2=6, tail_s=0.)

    def test_packing_and_dark_warning(self):
        raw = np.zeros((5,4), np.uint32)
        raw[:,0] = np.int32(-256).view(np.uint32)
        raw[:,1] = np.uint32(100 | (101<<16))
        raw[:,2] = np.uint32(6000 | (65535<<16))
        raw[0,1] = 101<<16 # intentional off, unknown uncalibrated dark power
        raw[0,3] = 2       # sensor below calibrated range
        result = shots.unpack(raw, sample_rate_hz=1000, status=(5<<8)|4, power_per_code=.01)
        self.assertEqual(result['error_power'][1], -.01)
        self.assertEqual(result['reference_power'][1], 1.)
        self.assertEqual(result['raw_adc_counts'][1], -1)
        self.assertTrue(result['valid'].all())
        metrics = analysis.shot_metrics(result)
        self.assertAlmostEqual(metrics['error_rms_power'], .01)
        self.assertEqual(metrics['off_actuator_max_codes'], 6000.)
        raw[1,3] = 2
        result = shots.unpack(raw, sample_rate_hz=1000, status=(5<<8)|4)
        self.assertFalse(analysis.shot_metrics(result)['usable'])

    def test_receive_armed_before_trigger_and_short_record_saved(self):
        ol, registers, events = mock_overlay()
        with patch.dict(sys.modules, {'pynq': SimpleNamespace(allocate=Buffer)}):
            armed = shots.arm(ol, maximum_samples=100, decimation_log2=6)
        self.assertEqual(events[0][0], 'receive_armed')
        self.assertEqual(events[1][0], 'control')
        armed['buffer'][0] = [0, 100|(100<<16), 5000, 0]
        registers[8] = (1<<8)|4
        ol.intensity_shot_dma.recvchannel.idle = True
        ol.intensity_shot_dma.recvchannel.transferred = 16
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'shot.npz'
            result = shots.finish(ol, armed, path=path, metadata={'power_units':'counts'})
            self.assertEqual(result['samples'], 1)
            self.assertTrue(result['complete'])
            with np.load(path, allow_pickle=False) as record:
                self.assertEqual(record['raw'].shape, (1,4))
        self.assertTrue(armed['buffer'].freed)
        self.assertEqual(registers[0], 0)

    def test_dma_mismatch_is_not_silently_saved(self):
        ol, registers, events = mock_overlay()
        with patch.dict(sys.modules, {'pynq': SimpleNamespace(allocate=Buffer)}):
            armed = shots.arm(ol, maximum_samples=100)
        registers[8] = (10<<8)|4
        ol.intensity_shot_dma.recvchannel.idle = True
        ol.intensity_shot_dma.recvchannel.transferred = 16
        with self.assertRaisesRegex(RuntimeError, 'byte count'):
            shots.finish(ol, armed, path='should_not_exist.npz')
        self.assertTrue(armed['buffer'].freed)

    def test_automatic_adaptation_is_certified_bounded_and_between_shots(self):
        configuration = dict(control_word=131, registers={'kp_q12':1000,
            'inverse_power_scale_q20':2*2**20, 'configuration_epoch':1},
            feature_version=1, power_units='mW', power_per_code=200/65536,
            power_full_scale_mW=200., effective_power_mW=100., sensor_mode='low_power',
            sensor_calibration_sha256='sensor', aom_calibration_sha256='aom',
            rf_chain={'lo_hz':90e6},
            maximum_measured_command_codes=21335, aom_alpha_rad_per_code=4.72156e-5,
            status={'active':True, 'shot_active':False})
        manual = {0:0, 8:1234}
        writes = []
        def write(a,v):
            manual[a] = v
            writes.append((a,v))
        ol = SimpleNamespace(axi_gpio_11=SimpleNamespace(read=lambda a:manual[a],write=write),
                             intensity_shot_control=SimpleNamespace(read=lambda a:0),
                             axi_dma_6=SimpleNamespace(sendchannel=SimpleNamespace(idle=True)))
        applications = []
        def apply(overlay, power, maximum_step_fraction):
            self.assertEqual(manual, {0:1, 8:0})
            power = np.clip(power, 100*(1-maximum_step_fraction), 100*(1+maximum_step_fraction))
            applications.append(power)
            configuration['registers']['inverse_power_scale_q20'] = round(200/power*2**20)
            configuration['effective_power_mW'] = float(power)
            return dict(effective_power_mW=float(power))
        def table(**kwargs):
            u = np.arange(kwargs['minimum_command_codes'],kwargs['maximum_command_codes']+1)
            return dict(u_codes=u,F_relative=np.sin(u*kwargs['alpha_rad_per_code'])**2)
        servo = SimpleNamespace(configuration=lambda ol:deepcopy(configuration),
                                status=lambda ol:configuration['status'],
                                aom_table=table,apply_incident_power=apply)
        t = np.arange(10000)/100000.
        illuminated = (t>=.001)&(t<.098)
        power = 110*.3*illuminated
        command = np.arcsin(np.sqrt(.3))/configuration['aom_alpha_rad_per_code']*illuminated
        record = dict(time_s=t,reference_power=power,measured_power=power,actuator_codes=command,
                      complete=True,valid=np.ones(len(t),bool),clipped=np.zeros(len(t),bool),
                      sample_rate_hz=100000.)
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {'intensity_servo':servo}):
            path = Path(directory)/'shot.npz'
            analysis.save_record(path,record,{'servo_configuration_start':deepcopy(configuration)})
            options = dict(optimizer_certified=False,controller_signature=shots.controller_signature(configuration),
                           nominal_power_mW=100.,state_path=str(Path(directory)/'state.json'))
            result = shots.adapt_after_shot(ol,path,options)
            self.assertFalse(result['applied'])
            self.assertEqual(applications,[])
            options['optimizer_certified'] = True
            result = shots.adapt_after_shot(ol,path,options)
            self.assertTrue(result['applied'])
            self.assertEqual(len(applications),1)
            self.assertLessEqual(applications[0],105.)
            self.assertEqual(manual,{0:0,8:1234})
            state = json.loads(Path(options['state_path']).read_text())
            self.assertAlmostEqual(state['estimate']['power'],110.,delta=.2)
            self.assertTrue(path.with_suffix('.adaptation.json').exists())

    def test_signature_detects_rf_changes_but_allows_intended_power_update(self):
        config = dict(control_word=131, registers={'kp_q12':1000, 'inverse_power_scale_q20':2**20,
                                                   'configuration_epoch':5},
                      rf_chain={'phase_deg':0., 'lo_mhz':90.}, power_units='mW')
        signature = shots.controller_signature(config)
        config['registers']['inverse_power_scale_q20'] = 2*2**20
        config['registers']['configuration_epoch'] += 1
        self.assertEqual(signature, shots.controller_signature(config))
        config['rf_chain']['phase_deg'] = 90.
        self.assertNotEqual(signature, shots.controller_signature(config))


if __name__ == '__main__':
    unittest.main()
