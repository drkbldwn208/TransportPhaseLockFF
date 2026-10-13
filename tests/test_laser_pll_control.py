"""Host-side checks for PYNQ register units, atomic update protocol and flags."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
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
        self.ol=SimpleNamespace(pll_frequency=GPIO(),pll_control=GPIO(),pll_status=GPIO(),
                                pll_acquisition=GPIO(),pll_acquisition_status=GPIO(),
                                pll_tracking=GPIO(),pll_monitor=GPIO(),pll_fra=GPIO(),pll_iir=GPIO())
        self.ol.pll_acquisition_status.values[8]=0xA8000000

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

    def test_old_stage3_mapping_is_rejected_before_writes(self):
        self.ol.pll_acquisition_status.values[8]=0xA3000000
        with self.assertRaisesRegex(ValueError,'A8 dual-PLL'):
            pll.configure(self.ol)
        self.assertEqual(self.ol.pll_control.writes,[])
        self.assertEqual(self.ol.pll_acquisition.writes,[])

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
            'ADC_Mixer_Type03':'1','ADC_Nyquist03':'0','ADC0_Sampling_Rate':'1.96608',
            'DAC_Data_Width11':'14','DAC_Interpolation_Mode11':'4'}}}
        self.ol.pll_status.values[0]=1<<22
        xrfdc=SimpleNamespace(EVNT_SRC_IMMEDIATE=0,MIXER_TYPE_FINE=2,
                             MIXER_MODE_C2R=3,MIXER_SCALE_1P0=1,EVENT_MIXER=1)
        with patch.dict('sys.modules',xrfdc=xrfdc): pll.configure(self.ol)
        self.assertEqual(calls,['reset',('update',1)])
        self.assertEqual(dac.MixerSettings['Freq'],0)
        self.assertEqual(dac.MixerSettings['PhaseOffset'],0)
        self.assertFalse(self.ol.pll_control.values[0]&1)
        self.assertTrue(self.ol.pll_control.values[0]&4)
        self.assertEqual(self.ol.pll_acquisition.values[0],0x00200041)

    def test_stage_request_preserves_fields_and_clears_dc(self):
        self.ol.pll_acquisition.values[0]=0x00200045
        pll.select_stage(self.ol,3,wait=False)
        self.assertEqual(self.ol.pll_acquisition.values[0],0x00200043)
        with self.assertRaises(ValueError): pll.enable_capture(self.ol,False)

    def test_dc_literal_signed_code(self):
        self.ol.pll_acquisition.values[0]=0x00200043
        self.ol.pll_control.values[0]=5
        pll.set_dc_output(self.ol,-8192)
        self.assertEqual(self.ol.pll_acquisition.values[8],0xe000)
        self.assertEqual(self.ol.pll_acquisition.values[0],0x00200047)
        self.assertEqual(self.ol.pll_control.values[0],5)

    def test_acquisition_status_units(self):
        self.ol.pll_acquisition_status.values[0]=3|128|(0xffffff<<8)
        self.ol.pll_acquisition_status.values[8]=0xA8010000|1024|417
        state=pll.acquisition_status(self.ol)
        self.assertEqual(state['remembered_turns'],-1)
        self.assertEqual(state['fft_frequency_hz'],800640000)
        self.assertTrue(state['fft_valid'])
        self.assertEqual(state['stage'],3)

    def test_stage_wait_timeout_restores_request(self):
        self.ol.pll_control.values[0]=1
        self.ol.pll_acquisition.values[0]=0x00200041
        with patch.object(pll.time,'monotonic',side_effect=[0,2]):
            with self.assertRaises(TimeoutError): pll.select_stage(self.ol,3,timeout_s=1)
        self.assertEqual(self.ol.pll_acquisition.values[0],0x00200041)

    def test_acquisition_parameters_require_mute(self):
        self.ol.pll_control.values[0]=1
        with self.assertRaises(ValueError): pll.configure_acquisition(self.ol)
        self.assertEqual(self.ol.pll_acquisition.writes,[])

    def test_tracking_stage_encoding_and_legacy_gain_protection(self):
        self.ol.pll_control.values[0]=1
        self.ol.pll_acquisition_status.values[0]=3|128
        self.ol.pll_acquisition.values[0]=0x00200043
        pll.select_stage(self.ol,4,wait=False)
        self.assertEqual(self.ol.pll_acquisition.values[0],0x00200048)
        with self.assertRaises(ValueError): pll.set_gains(self.ol,phase_gain_shift=1,capture_gain_shift=6)
        with self.assertRaises(ValueError): pll.enable_capture(self.ol,False)
        pll.select_stage(self.ol,3,wait=False)
        self.assertEqual(self.ol.pll_acquisition.values[0],0x00200043)

    def test_tracking_requires_settled_stage3(self):
        for state in (2,3|8,3|16,5):
            self.ol.pll_acquisition_status.values[0]=state
            with self.assertRaises(ValueError): pll.select_stage(self.ol,4,wait=False)
        self.assertEqual(self.ol.pll_acquisition.writes,[])

    def test_tracking_gain_units_and_status(self):
        self.ol.pll_acquisition_status.values[0]=4
        self.ol.pll_tracking.values[8]=(1<<31)|(1<<28)|(104858<<3)
        state=pll.set_tracking_gain(self.ol,3)
        self.assertEqual(self.ol.pll_tracking.writes,[(0,(14<<4)|3)])
        self.assertEqual(state['gain_relative_to_stage3'],8.0)
        self.assertTrue(state['initialized'] and state['valid'])
        self.assertFalse(state['ramping'])
        for shift in (-1,9):
            with self.assertRaises(ValueError): pll.set_tracking_gain(self.ol,shift)

    def test_tracking_timeout_leaves_requested_ramp_intact(self):
        self.ol.pll_acquisition_status.values[0]=4
        with patch.object(pll.time,'monotonic',side_effect=[0,2]):
            with self.assertRaises(TimeoutError): pll.set_tracking_gain(self.ol,2,timeout_s=1)
        self.assertEqual(self.ol.pll_tracking.values[0],(14<<4)|2)

    def capture_fixture(self, flags=0):
        # A tiny signed buffer with the physical {I64,Q64} DMA packing.
        released=[]
        class Buffer(np.ndarray):
            def freebuffer(self): released.append(True)
        buffer=np.zeros((16,2),dtype=np.int64).view(Buffer)
        receiver=SimpleNamespace(idle=False, transfer=lambda b:None, wait=lambda:None)
        self.ol.axi_dma_3=SimpleNamespace(recvchannel=receiver,mmio=SimpleNamespace(read=lambda _:0))
        old_write=self.ol.pll_monitor.write
        def write(address,value):
            old_write(address,value)
            if value&1:
                buffer[:,0]=-512; buffer[:,1]=1024
                self.ol.pll_monitor.values[8]=(16<<12)|2|flags
                receiver.idle=True
        self.ol.pll_monitor.write=write
        self.ol.pll_control.values[0]=1
        return buffer,released

    def test_iq_capture_units_and_no_laser_control_writes(self):
        buffer,released=self.capture_fixture()
        with patch.dict('sys.modules',pynq=SimpleNamespace(allocate=lambda **_:buffer)):
            capture=pll.capture_iq(self.ol,16,decimation_log2=4)
        np.testing.assert_array_equal(capture['i_adc_counts'],4*np.ones(16))
        np.testing.assert_array_equal(capture['q_adc_counts'],-2*np.ones(16))
        self.assertEqual(capture['sample_rate_hz'],15.36e6)
        self.assertEqual(self.ol.pll_monitor.values[0],0)
        self.assertEqual(self.ol.pll_control.writes,[])
        self.assertEqual(self.ol.pll_acquisition.writes,[])
        self.assertEqual(released,[True])

    def test_invalid_or_dropped_iq_is_rejected(self):
        for flag in (4,8):
            buffer,released=self.capture_fixture(flags=flag)
            with patch.dict('sys.modules',pynq=SimpleNamespace(allocate=lambda **_:buffer)):
                with self.assertRaisesRegex(RuntimeError,'lost/invalid'): pll.capture_iq(self.ol,16)
            self.assertEqual(released,[True])
            self.assertEqual(self.ol.pll_monitor.values[0],0)

    def test_4g4_reference_alias_and_reported_rf(self):
        self.ol.rf_band_base_hz=2*pll.ADC_SAMPLE_RATE_HZ
        self.ol.pll_status.values[0]=1<<22
        actual=pll.set_reference_frequency(self.ol,4.4e9)
        self.assertAlmostEqual(actual,4.4e9,places=4)
        word=self.ol.pll_frequency.read(0) | ((self.ol.pll_frequency.read(8)&65535)<<32)
        self.assertAlmostEqual(word*pll.ADC_SAMPLE_RATE_HZ/2**48,467840000,places=5)
        self.ol.pll_acquisition_status.values[8]=0xA8000000|244|1024
        self.assertAlmostEqual(pll.acquisition_status(self.ol)['fft_frequency_hz'],
                               2*pll.ADC_SAMPLE_RATE_HZ+244*pll.ADC_SAMPLE_RATE_HZ/1024)
        with self.assertRaises(ValueError): pll.set_reference_frequency(self.ol,3.8e9)

    def test_independent_channel_handles(self):
        names=('frequency','control','status','acquisition','acquisition_status','tracking','monitor',
               'fra','fra_window','fra_tone','fra_error','fra_drive','fra_counts','fra_extrema',
               'fra_samples','iir','iir_feed','iir_pole')
        for name in names: setattr(self.ol,'pll2_'+name,GPIO())
        self.ol.pll2_iq_dma=object(); self.ol.ip_dict={}; self.ol.usp_rf_data_converter_0=object()
        second=pll.channel(self.ol,1)
        pll.enable(second)
        self.assertEqual(second.pll_control.read(0),1)
        self.assertEqual(self.ol.pll_control.read(0),0)
        self.assertIs(second.axi_dma_3,self.ol.pll2_iq_dma)
        self.assertEqual((second.adc_tile,second.adc_block,second.dac_block),(1,1,3))

    def test_lead_lag_coefficients_match_analog_response(self):
        self.ol.pll_iir_feed=GPIO(); self.ol.pll_iir_pole=GPIO()
        write=self.ol.pll_iir.write
        def ack(address,value):
            write(address,value)
            self.ol.pll_iir.values[8]=value & 3
        self.ol.pll_iir.write=ack
        result=pll.configure_lead_lag(self.ol,zero_hz=20000,pole_hz=100000)
        f=np.geomspace(10,1e6,1000)
        z=np.exp(2j*np.pi*f/pll.IIR_SAMPLE_RATE_HZ)
        measured=(result['b0']+result['b1']/z)/(1+result['a1']/z)
        analog=(1+1j*f/20000)/(1+1j*f/100000)
        self.assertLess(np.max(np.abs(measured/analog-1)),0.001)
        self.assertAlmostEqual(result['dc_gain'],1,places=6)
        self.assertEqual(self.ol.pll_iir.read(0) & 1,0)
        result=pll.configure_lead_lag(self.ol,zero_hz=1400,pole_hz=24)
        self.assertAlmostEqual(result['dc_gain'],1,places=5)

    def test_iir_invalid_coefficients_do_not_write(self):
        self.ol.pll_iir_feed=GPIO(); self.ol.pll_iir_pole=GPIO()
        for b0,b1,a1 in ((1,0,-1),(1,0,1),(16,0,0),(1,0,float('nan'))):
            with self.assertRaises(ValueError): pll.set_iir_coefficients(self.ol,b0=b0,b1=b1,a1=a1)
        self.assertEqual(self.ol.pll_iir_feed.writes,[])
        self.ol.pll_iir.values[0]=1
        with self.assertRaisesRegex(ValueError,'bypass'): pll.set_iir_coefficients(self.ol,b0=1,b1=0,a1=0)



if __name__=='__main__': unittest.main()
