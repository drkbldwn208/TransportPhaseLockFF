"""Host protocol and physical units of the A6 frequency response measurement."""
import math
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
            'pll_tracking','pll_fra','pll_fra_window','pll_fra_tone','pll_fra_error','pll_fra_drive')})
        self.ol.pll_control.values[0]=1
        self.ol.pll_acquisition_status.values={0:3|128|64,8:0xA6000000}
        self.ol.pll_tracking.values[8]=104858
        self.faults=0; self.fresh=True; self.change_config=False
        original_write=self.ol.pll_fra.write
        def write(offset,value):
            original_write(offset,value)
            self.ol.pll_fra.values[8]=(4|self.faults) if value else 0
            if not value: return
            n=self.ol.pll_fra_window.read(8)
            for ip,z in ((self.ol.pll_fra_error,-20+4j),(self.ol.pll_fra_drive,10+2j)):
                ip.values.update({0x10:1,0x2C:int(self.fresh),0x4C:int(self.fresh)})
                for address,amplitude in ((0x20,z.real),(0x40,z.imag)):
                    bits=round(amplitude*n*32768/2)&((1<<72)-1)
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
        with self.assertRaises(ValueError): fra.frequency_plan(10,measure_cycles=1000)
        self.assertEqual(self.ol.pll_fra.writes,[])

    @patch.object(fra.time,'sleep')
    def test_fresh_phasors_units_and_cleanup(self,sleep):
        result=fra.measure_point(self.ol,1000)
        self.assertAlmostEqual(result['error'],-20+4j)
        self.assertAlmostEqual(result['drive'],10+2j)
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

    @patch.object(fra.time,'sleep')
    def test_saved_response_sign_and_scatter(self,sleep):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sweep.csv'
            rows=fra.sweep(self.ol,[20,1e6],csv_path=path)
            self.assertEqual(len(path.read_text().splitlines()),3)
            for row in rows:
                loop=complex(row['loop_re'],row['loop_im'])
                self.assertAlmostEqual(loop,-(-20+4j)/(10+2j))
                self.assertTrue(row['reliable'])
                self.assertTrue(math.isfinite(row['frequency_hz']))


if __name__=='__main__': unittest.main()
