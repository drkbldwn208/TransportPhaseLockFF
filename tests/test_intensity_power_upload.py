"""Physical-unit upload, mode scaling, legacy isolation and trigger-independent packing."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python_scripts'))
import intensity_servo as servo
from tp_intensity_rfsoc_buffer import TpIntensityBufferController
from tp_intensity_zmq_server import load_request
from test_intensity_linearized_helper import Board
from test_intensity_shots import Buffer

# Only device registration is unavailable off the BLACS host; use real H5 data
# and real serializer/decoder/conversion code throughout the measurements below.
with patch.dict(sys.modules, {'labscript': SimpleNamespace(IntermediateDevice=object),
    'labscript_devices': SimpleNamespace(),
    'labscript_devices.RedPitayaSPCM': SimpleNamespace(tp_int_ramp=None)}):
    import tp_intensity_host_schedule as host


class PowerUpload(unittest.TestCase):
    def setUp(self):
        self.ol = Board()
        servo.safe_off(self.ol)
        directory = ROOT/'exports/intensity_servo_20261028'
        low = servo.load_sensor_table(directory/'sensor_low_power.json')
        high = servo.load_sensor_table(directory/'sensor_high_power.json')
        tables = servo.make_sensor_luts(low, high, low_power_full_scale_mW=50)
        servo.load_calibration(self.ol, tables, servo.make_output_lut(), progress=False)
        servo.configure_controller(self.ol, servo.design_controller('PI'))
        servo.set_incident_power(self.ol, 184)
        servo.enable(self.ol)
        self.transfers = []
        send = SimpleNamespace(idle=True, running=True, stop=lambda:None, start=lambda:None,
                               transfer=lambda words:self.transfers.append(words.copy()))
        self.ol.axi_dma_6 = SimpleNamespace(sendchannel=send)
        self.ol.ip_dict['axi_dma_6'] = {}
        self.ol.axi_gpio_11.channel1 = SimpleNamespace(write=lambda value,mask:self.ol.axi_gpio_11.write(0,value))
        with patch.dict(sys.modules, {'pynq':SimpleNamespace(allocate=Buffer)}):
            self.controller = TpIntensityBufferController(overlay=self.ol,max_words=1000)

    def test_mw_roundtrip_both_modes_duration_and_metadata(self):
        for mode, scale in [('low_power',50),('high_power',200)]:
            servo.safe_off(self.ol)
            servo.configure_controller(self.ol, servo.design_controller('PI'), sensor_mode=mode)
            servo.enable(self.ol)
            header, points = host.power_request([0,.005,.1], [10,5,0], sensor_mode=mode)
            reply = load_request(self.controller, header, points.tobytes())
            words = self.transfers[-1]
            self.assertEqual(reply['power_per_code_mW'], scale/65536)
            self.assertEqual(words[0]>>16, round(10*65536/scale))
            self.assertEqual(words[-1], 0)
            self.assertAlmostEqual(np.sum((words[:-1].astype(np.uint64)&65535)+1)/servo.FS_HZ,.1)
            cfg = self.controller.loaded_metadata['servo_configuration_start']
            self.assertEqual(cfg['sensor_mode'], mode)
            self.assertIn('sensor_calibration_sha256', cfg)

    def test_wrong_units_mode_range_and_timing_rejected_before_dma(self):
        header, points = host.power_request([0,.1],[10,0],sensor_mode='high_power')
        with self.assertRaisesRegex(ValueError,'attenuation'):
            load_request(self.controller,header,points.tobytes())
        header['sensor_mode'] = 'low_power'
        header['power_units'] = 'W'
        with self.assertRaises(ValueError):
            load_request(self.controller,header,points.tobytes())
        for t,power in [([0,.1],[49,0]),([0,.1],[.01,0]),([0,.1],[-1,0]),
                        ([1,1.1],[10,0]),([0,1000],[10,0]),([0,.1],[float('nan'),0])]:
            with self.assertRaises(ValueError):
                self.controller.load_power_and_arm(t,power,sensor_mode='low_power')
        self.assertEqual(self.transfers,[])

    def test_legacy_words_do_not_silently_become_power_codes(self):
        words = np.array([(1000<<16)|24575,0],dtype=np.uint32)
        with self.assertRaisesRegex(ValueError,'command_units'):
            self.controller.load_and_arm(words)
        with self.assertRaisesRegex(ValueError,'different mode'):
            self.controller.load_and_arm(words,metadata=dict(command_units='power_codes',sensor_mode='high_power'))
        self.controller.load_and_arm(words,metadata=dict(command_units='power_codes',sensor_mode='low_power'))
        servo.safe_off(self.ol)
        with self.assertRaisesRegex(ValueError,'legacy'):
            self.controller.load_and_arm(words,metadata=dict(command_units='power_codes'))
        self.controller.load_and_arm(words,metadata=dict(command_units='adc_counts'))
        self.assertEqual(len(self.transfers),2)

    def test_explicit_h5_input_not_converted_ao(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'shot.h5'
            with h5py.File(path,'w') as f:
                d = f.create_dataset('/devices/pump/power_schedule',data=[[0.,10.],[.1,0.]])
                d.attrs.update(time_units='s',power_units='mW',sensor_mode='low_power')
            header, points = host.read_power_schedule(path,'pump')
            self.assertEqual(header['power_units'],'mW')
            np.testing.assert_array_equal(points,[[0,10],[.1,0]])
            self.assertIsNone(host.read_power_schedule(path,'other'))
            with h5py.File(path,'a') as f:
                f['/devices/pump/power_schedule'].attrs['power_units'] = 'V'
            with self.assertRaises(ValueError):
                host.read_power_schedule(path,'pump')

    def test_worker_selects_physical_dataset_without_legacy_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'shot.h5'
            with h5py.File(path,'w') as f:
                f.create_group('globals')
                d = f.create_dataset('/devices/pump/power_schedule',data=[[0.,10.],[.1,0.]])
                d.attrs.update(time_units='s',power_units='mW',sensor_mode='low_power')
            worker = host.TpIntensityStreamerWorker()
            worker.connection = 'dummy'
            worker.init()
            with patch.object(host,'compiled_h5_to_streamer_words',side_effect=AssertionError('Legacy conversion called')):
                worker.transition_to_buffered('pump',str(path),{},True)
            with h5py.File(path,'r') as f:
                saved = f['/results/tp_intensity_streamer'].attrs
                self.assertTrue(saved['loaded'])
                self.assertEqual(saved['source_power_units'],'mW')


if __name__ == '__main__':
    unittest.main()
