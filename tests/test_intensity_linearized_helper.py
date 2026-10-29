"""Physical/numerical checks and GPIO protocol smoke test, no PYNQ required."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('intensity_servo', ROOT/'python_scripts/intensity_servo.py')
servo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(servo)


class GPIO:
    def __init__(self, board, role):
        self.board, self.role, self.words = board, role, {0: 0, 8: 0}

    def read(self, address):
        b = self.board
        if self.role == 'read':
            return servo.FEATURE_VERSION if address == 8 else b.registers.get(b.address & 0x3ffff, 0)
        if self.role == 'control' and address == 8:
            ctrl = self.words[0]
            ready = all(b.counts[i] == n for i, n in enumerate((16384, 16384, 65536)))
            return int(bool(ctrl & 1) and ready) | (int(ready) << 1) | (1 << 6)
        return self.words[address]

    def write(self, address, value):
        b = self.board
        if self.role == 'write' and address == 0:
            changed = bool((b.address ^ value) & 0x80000000)
            b.address = value
            if changed:
                addr = value & 0x3ffff
                if addr >= servo.REGISTER_BASE:
                    b.registers[addr] = self.words[8]
                else:
                    bank = 0 if addr < 0x4000 else 1 if addr < 0x8000 else 2
                    b.counts[bank] += 1
                    b.registers[servo.REGISTER_BASE + 12 + bank] = b.counts[bank]
        self.words[address] = value


class Board:
    def __init__(self):
        self.registers, self.address, self.counts = {}, 0, [0, 0, 0]
        self.ip_dict = {name: {} for name in ('intensity_servo_read', 'intensity_servo_write', 'intensity_servo_control')}
        for name, role in [('intensity_servo_read', 'read'), ('intensity_servo_write', 'write'),
                           ('intensity_servo_control', 'control'), ('axi_gpio_9', 'plain'),
                           ('axi_gpio_11', 'plain'), ('fast_servo_controller_0', 'plain')]:
            setattr(self, name, GPIO(self, role))


class IntensityServoTests(unittest.TestCase):
    def test_calibration_units_monotonicity_and_resolution(self):
        folder = ROOT/'exports/intensity_servo_20261028'
        low = servo.load_sensor_table(folder/'sensor_low_power.json')
        high = servo.load_sensor_table(folder/'sensor_high_power.json')
        tables = servo.make_sensor_luts(low, high)
        self.assertEqual(tables['values'].shape, (2, 16384))
        self.assertEqual(tables['adc_limits_counts'], [[20, 12000], [20, 4500]])
        self.assertTrue(np.all(np.diff(tables['values'].astype(int), axis=1) >= 0))
        self.assertLess(abs(tables['values'][0, 12000] * 200/65536 - 46.979275), 200/65536/2)
        # Same ADC count represents more physical power in attenuated mode.
        self.assertGreater(tables['values'][1, 1000], tables['values'][0, 1000]*8)
        with self.assertRaises(ValueError):
            servo.make_sensor_luts(low, high, power_full_scale_mW=100)

    def test_aom_inverse_is_rising_capped_and_accurate(self):
        table = servo.make_output_lut()
        u = table['values'].astype(int)
        self.assertEqual(u[0], 0)
        self.assertEqual(u[-1], 21335)
        self.assertTrue(np.all(np.diff(u) >= 0))
        indices = np.arange(2000, table['maximum_fraction_code'], 37)
        recovered = np.sin(table['alpha_rad_per_code']*u[indices])**2
        # One actuator-code quantization changes F by at most alpha.
        self.assertLess(np.max(abs(recovered-indices/65536)), table['alpha_rad_per_code'])

    def test_two_ranges_preserve_physical_gain_and_improve_low_mode_rounding(self):
        folder = ROOT/'exports/intensity_servo_20261028'
        low = servo.load_sensor_table(folder/'sensor_low_power.json')
        high = servo.load_sensor_table(folder/'sensor_high_power.json')
        tables = servo.make_sensor_luts(low, high, low_power_full_scale_mW=50)
        x = np.arange(20, 12001)
        power = np.interp(x, low['adc_counts'], low['optical_power'])
        self.assertLessEqual(np.max(abs(tables['values'][0,x].astype(float)*50/65536-power)), 50/65536/2)
        self.assertTrue(np.all(np.diff(tables['values'][0,20:12001].astype(int)) > 0))
        board = Board()
        servo.safe_off(board)
        servo.load_calibration(board, tables, servo.make_output_lut(), progress=False)
        servo.configure_controller(board, servo.design_controller('PI'), sensor_mode='low_power')
        servo.set_incident_power(board, 184)
        configurations = []
        for mode, expected_scale in [('low_power',50),('high_power',200),('low_power',50)]:
            servo.configure_controller(board, servo.design_controller('PI'), sensor_mode=mode)
            cfg = servo.configuration(board)
            configurations.append(cfg)
            self.assertEqual(cfg['power_full_scale_mW'], expected_scale)
            self.assertEqual(cfg['power_per_code'], expected_scale/65536)
            self.assertLess(abs(cfg['effective_power_mW']-184), .002)
            # A fixed physical demand maps to the same normalized AOM power,
            # even though the reference and feedback coordinates change 4x.
            q = servo.power_codes(10, power_full_scale_mW=expected_scale)
            normalized = q/65536*cfg['registers']['inverse_power_scale_q20']/2**20
            self.assertLess(abs(normalized-10/184), 1e-5)
        self.assertEqual(configurations[0]['registers']['kp_q12'], configurations[1]['registers']['kp_q12'])
        self.assertAlmostEqual(configurations[0]['sensor_power_limits_mW']['low_power'][1], 46.979275, places=3)
        with self.assertRaises(ValueError):
            servo.set_incident_power(board, 184, power_full_scale_mW=200)

    def test_controller_coefficients_and_zero_corner(self):
        c = servo.design_controller('PIII')
        self.assertEqual(c['alpha_q24'], [343146, 858, 86])
        self.assertEqual(c['kp_q12'], 1445)
        fast = servo.design_controller('PI')
        self.assertEqual(fast['alpha_q24'], [42893, 0, 0])
        self.assertEqual(fast['kp_q12'], 4130)
        flat = servo.design_controller('PI', kp=.5, integral_corners_hz=[0])
        np.testing.assert_allclose(servo.controller_response([1e3, 1e5, 1e6], flat), .5)
        with self.assertRaises(ValueError):
            servo.design_controller('PI', integral_corners_hz=[2e6])

    def test_power_waveform_duration_and_final_zero(self):
        words = servo.waveform_words([0, .001, .003], [5, 10, 0])
        self.assertEqual(int(words[-1]), 0)
        duration = np.sum((words[:-1].astype(np.uint64) & 65535)+1) / servo.FS_HZ
        self.assertAlmostEqual(duration, .003)
        self.assertEqual(int(words[0] >> 16), servo.power_codes(5))
        with self.assertRaises(ValueError):
            servo.power_codes(200)
        # 1 us is 245.76 clocks. Independently rounding each hold would stretch
        # a 100 ms shot by ~98 us. Absolute-edge quantization stays within 0.5 clk.
        t = np.linspace(0, .1, 100001)
        words = servo.waveform_words(t, np.full(len(t), 5.))
        edges = np.cumsum((words[:-1].astype(np.uint64)&65535)+1)
        self.assertLessEqual(np.max(abs(edges-t[1:]*servo.FS_HZ)), .500001)

    def test_gpio_load_readback_and_no_active_rewrite(self):
        low = {'adc_counts': [20, 1000, 12000], 'optical_power': [.1, 4, 47], 'power_units': 'mW'}
        high = {'adc_counts': [20, 1000, 4500], 'optical_power': [1.8, 38, 168], 'power_units': 'mW'}
        board = Board()
        servo.safe_off(board)
        servo.load_calibration(board, servo.make_sensor_luts(low, high), servo.make_output_lut(), progress=False)
        servo.configure_controller(board, servo.design_controller('PI'))
        servo.set_incident_power(board, 184)
        servo.manual_power(board, 0)
        servo.enable(board)
        self.assertTrue(servo.status(board)['active'])
        self.assertEqual(board.axi_gpio_9.read(0), 0)
        servo.manual_power(board, 10)
        with self.assertRaises(ValueError):
            servo.manual_power(board, 50)  # Beyond low-mode sensor calibration.
        board.intensity_servo_control.words[0] |= 8
        with self.assertRaises(ValueError):
            servo.manual_power(board, 150)  # Inside high sensor range, beyond AOM headroom.
        board.intensity_servo_control.words[0] &= ~8
        servo.manual_power(board, 0)
        with self.assertRaises(RuntimeError):
            servo.configure_controller(board, servo.design_controller('PII'))
        applied = servo.apply_incident_power(board, 300)
        self.assertTrue(applied['limited'])
        self.assertLessEqual(applied['effective_power_mW'], 184*1.05 + .001)
        self.assertTrue(servo.status(board)['active'])


if __name__ == '__main__':
    unittest.main()
