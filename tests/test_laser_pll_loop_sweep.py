"""Host protocol and physical units of the A7 frequency response measurement."""
import math
import csv
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python_scripts'))
import laser_pll_loop_sweep as fra


class GPIO:
    def __init__(self): self.values={}; self.writes=[]
    def read(self,offset): return self.values.get(offset,0)
    def write(self,offset,value): self.values[offset]=value; self.writes.append((offset,value))


class Analyzer(unittest.TestCase):
    def setUp(self):
        self.ol=SimpleNamespace(**{name:GPIO() for name in (
            'pll_control','pll_frequency','pll_acquisition','pll_acquisition_status',
            'pll_tracking','pll_fra','pll_fra_window','pll_fra_tone','pll_fra_error','pll_fra_drive','pll_fra_counts','pll_fra_extrema','pll_fra_samples',
            'pll_iir','pll_iir_feed','pll_iir_pole')})
        self.ol.pll_control.values[0]=1
        self.ol.pll_acquisition_status.values={0:3|128|64,8:0xA7000000}
        self.ol.pll_tracking.values[8]=104858
        self.faults=0; self.fresh=True; self.change_config=False
        original_write=self.ol.pll_fra.write
        def write(offset,value):
            original_write(offset,value)
            self.ol.pll_fra.values[8]=(4|self.faults) if value else 0
            if not value: return
            n=self.ol.pll_fra_window.read(8)
            self.ol.pll_fra_samples.values[8]=n
            polarity=-1 if self.ol.pll_fra_tone.read(0x18) & (1<<19) else 1
            for ip,z in ((self.ol.pll_fra_error,-20+4j),(self.ol.pll_fra_drive,12+4j)):
                ip.values.update({0x10:1,0x2C:int(self.fresh),0x4C:int(self.fresh)})
                for address,amplitude in ((0x20,z.real),(0x40,z.imag)):
                    bits=round(polarity*amplitude*n*32768/2)&((1<<72)-1)
                    for k in range(3): ip.values[address+4*k]=(bits>>(32*k))&0xFFFFFFFF
            if self.change_config: self.ol.pll_control.values[0]^=16
        self.ol.pll_fra.write=write

    def test_frequency_and_window_units(self):
        for f in (10,20,100,1000,1e6):
            p=fra.frequency_plan(f)
            self.assertLessEqual(abs(p['frequency_hz']-f),0.458/2)
            cycles=p['measure_clocks']*p['frequency_hz']/fra.FS_HZ
            self.assertLessEqual(abs(cycles-p['measure_cycles']),p['frequency_hz']/fra.FS_HZ/2+1e-9)
        self.assertGreater(fra.frequency_plan(10)['duration_s'],2)

    def test_invalid_requests_do_not_write(self):
        for f in (0,9,1e6+1,float('nan')):
            with self.assertRaises(ValueError): fra.measure_point(self.ol,f)
        with self.assertRaises(ValueError): fra.measure_point(self.ol,100,amplitude_codes=0)
        with self.assertRaises(ValueError): fra.measure_point(self.ol,100,allow_clipping='False')
        with self.assertRaises(ValueError): fra.frequency_plan(10,measure_cycles=1000)
        self.assertEqual(self.ol.pll_fra.writes,[])

    @patch.object(fra.time,'sleep')
    def test_fresh_phasors_units_and_cleanup(self,sleep):
        result=fra.measure_point(self.ol,1000)
        self.assertAlmostEqual(result['error'],-20+4j)
        self.assertAlmostEqual(result['drive'],12+4j)
        self.assertEqual(self.ol.pll_fra.read(0),0)
        self.assertEqual(self.ol.pll_fra_tone.read(0x18),0)
        for ip in (self.ol.pll_control,self.ol.pll_frequency,self.ol.pll_tracking,self.ol.pll_acquisition):
            self.assertEqual(ip.writes,[])

    @patch.object(fra.time,'sleep')
    def test_all_faults_rejected_and_tone_removed(self,sleep):
        for bit in range(3,8):
            self.faults=1<<bit
            with self.assertRaisesRegex(RuntimeError,'Rejecting transfer'): fra.measure_point(self.ol,1000)
            self.assertEqual(self.ol.pll_fra.read(0),0)
            self.assertEqual(self.ol.pll_fra_tone.read(0x18),0)

    @patch.object(fra.time, 'sleep')
    def test_allow_clipping_returns_phasors_flags_and_cleans_up(self, sleep):
        self.faults = 1 << 3
        point = fra.measure_point(self.ol, 1000, allow_clipping=True)
        self.assertTrue(point['clipped'])
        self.assertTrue(point['allow_clipping'])
        self.assertEqual(point['status'] & (1 << 3), 1 << 3)
        self.assertAlmostEqual(point['error'], -20+4j)
        self.assertAlmostEqual(point['drive'], 12+4j)
        self.assertEqual(self.ol.pll_fra.read(0), 0)
        self.assertEqual(self.ol.pll_fra_tone.read(0x18), 0)
        self.assertEqual(self.ol.pll_control.writes, [])

    @patch.object(fra.time, 'sleep')
    def test_allow_clipping_does_not_hide_other_faults(self, sleep):
        for bit in range(4, 8):
            self.faults = (1 << 3) | (1 << bit)
            with self.assertRaisesRegex(RuntimeError, 'Rejecting transfer'):
                fra.measure_point(self.ol, 1000, allow_clipping=True)
            self.assertEqual(self.ol.pll_fra_tone.read(0x18), 0)

    @patch.object(fra.time, 'sleep')
    def test_sweep_keeps_and_saves_clipped_repeats_without_claiming_reliability(self, sleep):
        original_measure = fra.measure_point
        count = 0
        def measure(*args, **kwargs):
            nonlocal count
            self.faults = (1 << 3) if count % 3 == 0 else 0
            count += 1
            return original_measure(*args, **kwargs)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'clipped.csv'
            with patch.object(fra, 'measure_point', side_effect=measure):
                rows = fra.sweep(self.ol, [100, 1000], repeats=3,
                                 allow_clipping=True, csv_path=path)
            with path.open() as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual(len(saved), 2)
            for row, disk in zip(rows, saved):
                self.assertEqual(row['clipped_repeats'], 1)
                self.assertTrue(row['repeat_consistent'])
                self.assertTrue(row['clipped'])
                self.assertFalse(row['reliable'])
                self.assertEqual(disk['clipped_repeats'], '1')
                self.assertEqual(disk['reliable'], 'False')
                self.assertAlmostEqual(complex(row['loop_re'], row['loop_im']),
                                       -(-20+4j)/(12+4j))

    @patch.object(fra.time,'sleep')
    def test_stale_result_rejected(self,sleep):
        self.fresh=False
        with self.assertRaisesRegex(RuntimeError,'fresh complete'): fra.measure_point(self.ol,1000)

    @patch.object(fra.time,'sleep')
    def test_changed_configuration_rejected(self,sleep):
        self.change_config=True
        with self.assertRaisesRegex(RuntimeError,'settings changed'): fra.measure_point(self.ol,1000)

    def test_old_bitstream_rejected_before_writes(self):
        self.ol.pll_acquisition_status.values[8]=0xA5000000
        with self.assertRaises(ValueError): fra.measure_point(self.ol,1000)
        self.assertEqual(self.ol.pll_fra_tone.writes,[])

    def test_old_python_helper_explained_before_writes(self):
        with patch.object(fra, 'laser_pll', SimpleNamespace(__file__='/notebook/laser_pll.py')):
            with self.assertRaisesRegex(RuntimeError, 'Copy both A7 Python helpers'):
                fra.measure_point(self.ol, 1000)
        self.assertEqual(self.ol.pll_fra_tone.writes, [])

    @patch.object(fra.time, 'sleep')
    def test_no_dependency_on_private_control_helpers(self, sleep):
        public_helper = SimpleNamespace(
            FPGA_VERSION=0xA7,
            acquisition_status=fra.laser_pll.acquisition_status,
            tracking_status=fra.laser_pll.tracking_status)
        with patch.object(fra, 'laser_pll', public_helper):
            result = fra.measure_point(self.ol, 1000)
        self.assertAlmostEqual(result['error'], -20+4j)

    def test_missing_analyzer_hwh_explained_before_writes(self):
        del self.ol.pll_fra_error
        with self.assertRaisesRegex(ValueError, 'matching A7 HWH'):
            fra.measure_point(self.ol, 1000)
        self.assertEqual(self.ol.pll_fra_tone.writes, [])

    @patch.object(fra.time,'sleep')
    def test_saved_response_sign_and_scatter(self,sleep):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sweep.csv'
            rows=fra.sweep(self.ol,[20,1e6],csv_path=path)
            self.assertEqual(len(path.read_text().splitlines()),3)
            for row in rows:
                loop=complex(row['loop_re'],row['loop_im'])
                self.assertAlmostEqual(loop,-(-20+4j)/(12+4j))
                self.assertTrue(row['reliable'])
                self.assertTrue(math.isfinite(row['frequency_hz']))

    @patch.object(fra.time, 'sleep')
    def test_window_diagnostics_preserve_signed_extrema(self, sleep):
        self.ol.pll_fra_counts.values={0:7,8:19}
        self.ol.pll_fra_extrema.values={0:(234<<16)|((-123)&65535),8:(245<<16)|((-130)&65535)}
        self.ol.pll_fra_samples.values[0]=200
        point=fra.measure_point(self.ol,1000)
        diag=point['diagnostics']
        self.assertEqual(diag['error_range_codes'],(-123,234))
        self.assertEqual(diag['drive_range_codes'],(-130,245))
        self.assertEqual(diag['outside_clip_samples'],200)
        self.assertEqual(diag['dac_clip_samples'],7)

    @patch.object(fra.time, 'sleep')
    def test_clipped_blocks_skipped_and_all_clipped_point_does_not_abort(self, sleep):
        self.faults=8
        rows=fra.sweep(self.ol,[100,1000],repeats=2,max_repeats=3)
        for row in rows:
            self.assertEqual(row['repeats'],0)
            self.assertEqual(row['clipped_repeats'],3)
            self.assertFalse(row['reliable'])
            self.assertTrue(math.isnan(row['loop_re']))

    @patch.object(fra.time, 'sleep')
    def test_noisy_response_extends_integration_and_stays_flagged(self, sleep):
        original=fra.measure_point
        count=0
        def disturbed(*args,**kwargs):
            nonlocal count
            p=original(*args,**kwargs)
            # A random-phase background appears in E and U equally; D is known.
            noise=100j if count%2 else -100j
            count+=1
            p['error']+=noise; p['drive']+=noise
            return p
        with patch.object(fra,'measure_point',side_effect=disturbed):
            row=fra.sweep(self.ol,[1000],repeats=2,max_repeats=6)[0]
        self.assertEqual(row['attempts'],6)
        self.assertFalse(row['reliable'])
        self.assertGreater(row['drive_stderr_codes'],10)

    @patch.object(fra.time, 'sleep')
    def test_opposite_probe_preserves_phasor_sign(self, sleep):
        positive=fra.measure_point(self.ol,1000,polarity=1)
        negative=fra.measure_point(self.ol,1000,polarity=-1)
        self.assertEqual(positive['error'],negative['error'])
        self.assertEqual(positive['drive'],negative['drive'])



if __name__=='__main__': unittest.main()
