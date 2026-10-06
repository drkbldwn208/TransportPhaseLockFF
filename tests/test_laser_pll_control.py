"""Host-side checks for PYNQ register units, atomic update protocol and flags."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('laser_pll',Path(__file__).resolve().parents[1]/'python_scripts/laser_pll.py')
pll=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pll)


class GPIO:
    def __init__(self):
        self.values={0:0,8:0}
        self.writes=[]
    def read(self, address):
        return self.values[address]
    def write(self, address, value):
        self.values[address]=value
        self.writes.append((address,value))


class Controls(unittest.TestCase):
    def setUp(self):
        self.ol=SimpleNamespace(pll_frequency=GPIO(),pll_control=GPIO(),pll_status=GPIO())

    def test_frequency_units_and_commit_order(self):
        self.ol.pll_status.values[0]=1<<22
        actual=pll.set_reference_frequency(self.ol,800e6)
        self.assertAlmostEqual(actual,800e6,places=5)
        writes=self.ol.pll_frequency.writes
        self.assertEqual([a for a,_ in writes],[0,8])
        word=round(800e6/pll.ADC_SAMPLE_RATE_HZ*(1<<48))
        self.assertEqual(writes[0][1],word&0xffffffff)
        self.assertEqual(writes[1][1],(word>>32)|(1<<16))
        self.ol.pll_status.values[0]=0
        pll.set_reference_frequency(self.ol,801e6)
        self.assertEqual(self.ol.pll_frequency.values[8]>>16,0)

    def test_reset_requires_muted_output(self):
        self.ol.pll_control.values[0]=1
        with self.assertRaises(ValueError): pll.set_reference_frequency(self.ol,800e6,restart_phase=True)
        self.assertEqual(self.ol.pll_frequency.writes,[])

    def test_bad_frequency_does_not_write(self):
        for frequency in [0,-1,1e9,float('nan'),float('inf')]:
            with self.assertRaises(ValueError): pll.set_reference_frequency(self.ol,frequency)
        self.assertEqual(self.ol.pll_frequency.writes,[])

    def test_capture_toggle_preserves_gain_and_enable(self):
        value=(64<<16)|(6<<8)|1
        self.ol.pll_control.values[0]=value
        pll.enable_capture(self.ol)
        self.assertEqual(self.ol.pll_control.values[0],value|2)
        pll.enable_capture(self.ol,False)
        self.assertEqual(self.ol.pll_control.values[0],value)
        pll.enable(self.ol,False)
        self.assertEqual(self.ol.pll_control.values[0],value&~1)

    def test_signed_status_units(self):
        self.ol.pll_status.values[0]=(1<<19)|(1<<18)|((-65536)&0x3ffff)
        self.ol.pll_status.values[8]=(-1000)&0xffffffff
        s=pll.status(self.ol)
        self.assertAlmostEqual(s['phase_error_rad'],-pll.math.pi/2)
        self.assertEqual(s['frequency_error_hz'],-937500)
        self.assertTrue(s['valid'] and s['enabled'])

    def test_gain_update_is_one_write_and_preserves_flags(self):
        original=(321<<16)|7|(6<<8)
        self.ol.pll_control.values[0]=original
        pll.set_gains(self.ol,phase_gain_shift=3,capture_gain_shift=5)
        self.assertEqual(self.ol.pll_control.writes,[(0,(321<<16)|7|(3<<4)|(5<<8))])
        with self.assertRaises(ValueError): pll.set_gains(self.ol,phase_gain_shift=-1,capture_gain_shift=5)

    def test_configuration_resets_dac_phase_and_leaves_output_muted(self):
        calls=[]
        dac=SimpleNamespace(MixerSettings={'Freq':80.0,'PhaseOffset':90.0},
                            ResetNCOPhase=lambda:calls.append('reset'),
                            UpdateEvent=lambda event:calls.append(('update',event)))
        self.ol.usp_rf_data_converter_0=SimpleNamespace(dac_tiles=[None,SimpleNamespace(blocks=[None,dac])])
        self.ol.ip_dict={'usp_rf_data_converter_0':{'parameters':{
            'ADC_Data_Type03':'0','ADC_Decimation_Mode03':'1','ADC_Data_Width03':'8',
            'ADC_Mixer_Type03':'1','ADC0_Sampling_Rate':'1.96608',
            'DAC_Data_Width11':'14','DAC_Interpolation_Mode11':'4'}}}
        self.ol.pll_status.values[0]=1<<22
        xrfdc=SimpleNamespace(EVNT_SRC_IMMEDIATE=0,MIXER_TYPE_FINE=2,
                             MIXER_MODE_C2R=3,MIXER_SCALE_1P0=1,EVENT_MIXER=1)
        with patch.dict('sys.modules',xrfdc=xrfdc): pll.configure(self.ol)
        self.assertEqual(calls,['reset',('update',1)])
        self.assertEqual(dac.MixerSettings['Freq'],0)
        self.assertEqual(dac.MixerSettings['PhaseOffset'],0)
        self.assertFalse(self.ol.pll_control.values[0]&1)


if __name__=='__main__': unittest.main()
