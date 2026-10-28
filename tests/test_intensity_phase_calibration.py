"""Notebook helper checks: signed phase, circular averaging and cumulative writes."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python_scripts'))
import intensity_phase_calibration as pc
class Buffer(np.ndarray):
    def freebuffer(self):self.freed=True
class Reg:
    def __init__(self,value=0):self.value=value;self.channel1=self
    def read(self,address):return self.value
    def write(self,*args,mask=None):self.value=args[-1]
class Calibration(unittest.TestCase):
    def test_correction_adds_to_existing_phase(self):
        gpio=Reg(10333)
        with patch.object(pc.time,'sleep'):
            result=pc.correct_phase(SimpleNamespace(axi_gpio_10=gpio),13070/8192)
        self.assertEqual(gpio.value,23403)
        self.assertAlmostEqual(result,23403/8192)
    def test_negative_two_complement_and_wrapping(self):
        gpio=Reg((-8192)&65535)
        with patch.object(pc.time,'sleep'):
            pc.correct_phase(SimpleNamespace(axi_gpio_10=gpio),-.5)
        self.assertEqual(gpio.value,(-12288)&65535)
    def test_circular_mean_and_actual_shorter_packet(self):
        freed=[]
        def allocate(**kw):
            a=np.zeros(kw['shape'],kw['dtype']).view(Buffer)
            a.freebuffer=lambda:freed.append(True)
            return a
        def transfer(a):
            a[:32]=0  # transient prefix is excluded
            a[32:256:2]=round((np.pi-.01)*8192)
            a[33:256:2]=round((-np.pi+.01)*8192)
            a[256]=0  # not transferred, must not enter phase estimator
        rx=SimpleNamespace(running=True,idle=True,transferred=512,transfer=transfer,wait=lambda:None)
        ol=SimpleNamespace(intensity_limits=Reg(0x494e5402),axi_gpio_8=Reg(),axi_dma_4=SimpleNamespace(recvchannel=rx))
        with patch.dict(sys.modules,pynq=SimpleNamespace(allocate=allocate)):
            result=pc.read_phase(ol,samples=256)
        self.assertAlmostEqual(abs(result['phase_rad']),np.pi)
        self.assertGreater(result['circular_concentration'],.999)
        self.assertEqual(freed,[True])
if __name__=='__main__':unittest.main()
