"""R7 phase-FRA physical units, known RF delay, closed-loop gain and fault cleanup."""
import cmath
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import test_laser_pll_loop_sweep as fixture
import laser_pll_phase_fra as pf


class PhaseFRA(unittest.TestCase):
    def setUp(self):
        f=fixture.Analyzer(); f.setUp(); self.ol=ol=f.ol
        ol.pll_rf_source=fixture.GPIO(); ol.pll_rf_source.values={0:8192,8:pf.FEATURE_VERSION}
        ol.pll_monitor=fixture.GPIO()
        ol.pll_status=SimpleNamespace(read=lambda _:((ol.pll_frequency.read(8)>>16)&1)<<22)
        ol.pll_acquisition_status.read=lambda address: (0xA7000000 if address==8 else
            128|(5 if ol.pll_acquisition.read(0)&4 else 3))
        block=lambda freq:SimpleNamespace(MixerSettings={'Freq':freq},ResetNCOPhase=Mock(),UpdateEvent=Mock())
        ol.usp_rf_data_converter_0=SimpleNamespace(
            adc_tiles=[SimpleNamespace(blocks=[None,None,None,block(0.)])],
            dac_tiles=[None,SimpleNamespace(blocks=[block(33.),block(0.),block(800.01),block(0.)])])
        ol.ip_dict={'usp_rf_data_converter_0':{'parameters':{
            'ADC_Data_Type03':'0','ADC_Decimation_Mode03':'1','ADC_Data_Width03':'8',
            'ADC_Mixer_Type03':'1','ADC_Nyquist03':'0','ADC0_Sampling_Rate':'1.96608',
            'DAC_Data_Width11':'14','DAC_Interpolation_Mode11':'4',
            'DAC_Data_Width12':'14','DAC_Interpolation_Mode12':'4'}}}
        self.constants=SimpleNamespace(EVNT_SRC_IMMEDIATE=0,MIXER_TYPE_FINE=2,MIXER_MODE_C2R=2,
                                        MIXER_SCALE_1P0=1,EVENT_MIXER=1)
        self.xrfdc=patch.dict(sys.modules,xrfdc=self.constants);self.xrfdc.start();self.addCleanup(self.xrfdc.stop)
        self.sleep=patch.object(pf.time,'sleep',lambda _:None);self.sleep.start();self.addCleanup(self.sleep.stop)
        self.fault=0;self.change_config=False;self.delay_s=403e-9
        def write(address,value):
            ol.pll_fra.values[address]=value;ol.pll_fra.writes.append((address,value))
            ol.pll_fra.values[8]=(4|self.fault|((3 if value==3 else 2)<<8)) if value else 0
            if not value:return
            n=ol.pll_fra_window.read(8);ol.pll_fra_samples.values[8]=n
            amplitude=ol.pll_fra_tone.read(0x18)
            if amplitude&1<<19:amplitude-=1<<20
            frequency=ol.pll_fra_tone.read(0x10)*8*pf.fra.FS_HZ/2**32
            delay=cmath.exp(-2j*math.pi*frequency*self.delay_s)
            if value==3:
                tx=amplitude*cmath.exp(-2j*math.pi*frequency*4/pf.fra.FS_HZ)
                rx=tx*delay
            else:
                assert value==5
                loop=.48*delay;tx=amplitude/(1+loop)
                rx=-.004*delay*tx*pf.PHASE_CODES_PER_RAD
            for ip,z in ((ol.pll_fra_error,rx),(ol.pll_fra_drive,tx)):
                ip.values.update({0x10:1,0x2c:1,0x4c:1})
                for address,v in ((0x20,z.real),(0x40,z.imag)):
                    raw=round(v*n*32768/2)&((1<<72)-1)
                    for k in range(3):ip.values[address+4*k]=raw>>(32*k)&0xffffffff
            if self.change_config:ol.pll_control.values[8]=ol.pll_control.read(8)^1
        ol.pll_fra.write=write

    def test_closed_phase_units_polarity_and_legacy_loop_recovery(self):
        for polarity in (1,-1):
            p=pf.measure_point(self.ol,100e3,polarity=polarity)
            delay=cmath.exp(-2j*math.pi*p['frequency_hz']*self.delay_s)
            self.assertAlmostEqual(p['response'],-.004*delay/(1+.48*delay))
            self.assertAlmostEqual((p['stimulus']-p['drive'])/p['drive'],.48*delay)
            self.assertEqual(self.ol.pll_fra.read(0),0)
            self.assertEqual(self.ol.pll_fra_tone.read(0x18),0)

    def test_rf_setup_correct_channel_dc_zero_and_known_delay(self):
        old_adc=dict(self.ol.usp_rf_data_converter_0.adc_tiles[0].blocks[3].MixerSettings)
        info=pf.setup_rf(self.ol)
        self.assertEqual(info['carrier_hz'],800.01e6)
        self.assertEqual(self.ol.pll_acquisition.read(8)&65535,0)
        self.assertEqual(self.ol.usp_rf_data_converter_0.dac_tiles[1].blocks[0].MixerSettings,{'Freq':33.})
        self.assertEqual(self.ol.usp_rf_data_converter_0.adc_tiles[0].blocks[3].MixerSettings,old_adc)
        for polarity in (1,-1):
            p=pf.measure_point(self.ol,1e6,mode='rf',polarity=polarity)
            self.assertAlmostEqual(p['response'],cmath.exp(-2j*math.pi*p['frequency_hz']*self.delay_s))
            self.assertAlmostEqual(abs(p['drive']),p['phase_amplitude_rad'])
        self.assertEqual(self.ol.pll_control.read(0)&1,1) # receiver still running
        self.assertEqual(self.ol.pll_rf_source.read(0),8192) # RF carrier unchanged after probe

    def test_old_image_and_missing_feature_rejected_before_writes(self):
        self.ol.pll_rf_source.values[8]=0
        with self.assertRaisesRegex(ValueError,'extension'):pf.measure_point(self.ol,1000)
        self.assertEqual(self.ol.pll_fra_tone.writes,[])
        self.assertEqual(self.ol.pll_control.writes,[])

    def test_rf_requires_zero_output_and_matched_carrier(self):
        pf.setup_rf(self.ol)
        self.ol.pll_acquisition.values[8]=100
        with self.assertRaisesRegex(ValueError,'DC code zero'):pf.measure_point(self.ol,1000,mode='rf')
        self.ol.pll_acquisition.values[8]=0
        self.ol.usp_rf_data_converter_0.dac_tiles[1].blocks[2].MixerSettings['Freq']=800.
        with self.assertRaisesRegex(ValueError,'match'):pf.measure_point(self.ol,1000,mode='rf')

    def test_faults_and_changed_settings_always_remove_probe(self):
        for fault in (8,16,32,64,128):
            self.fault=fault
            with self.assertRaises(RuntimeError):pf.measure_point(self.ol,1000)
            self.assertEqual(self.ol.pll_fra_tone.read(0x18),0)
        self.fault=8
        self.assertTrue(pf.measure_point(self.ol,1000,allow_clipping=True)['clipped'])
        self.fault=0;self.change_config=True
        with self.assertRaisesRegex(RuntimeError,'changed'):pf.measure_point(self.ol,1000)
        self.assertEqual(self.ol.pll_fra.read(0),0)

    def test_average_phasors_save_units_and_clipping_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'closed.csv'
            rows=pf.sweep(self.ol,[1e3,1e5],csv_path=path,repeats=2,max_repeats=2)
            self.assertTrue(all(r['reliable'] and r['loop_reliable'] for r in rows))
            self.assertEqual(rows[0]['response_units'],'rad/DAC-code')
            self.assertEqual(len(path.read_text().splitlines()),3)
            self.assertEqual(len(path.with_name('closed_blocks.csv').read_text().splitlines()),5)
            self.fault=8
            row=pf.sweep(self.ol,[1000],csv_path=path,repeats=2,max_repeats=2)[0]
            self.assertEqual(row['repeats'],0);self.assertFalse(row['reliable'])
            self.assertTrue(math.isnan(row['response_re']))
            row=pf.sweep(self.ol,[1000],csv_path=path,repeats=2,max_repeats=2,allow_clipping=True)[0]
            self.assertTrue(row['clipped']);self.assertFalse(row['reliable'])
            self.fault=0;pf.setup_rf(self.ol)
            row=pf.sweep(self.ol,[1e6],mode='rf',csv_path=path,repeats=2,max_repeats=2)[0]
            self.assertEqual(row['response_units'],'rad/rad');self.assertTrue(row['reliable'])
            self.assertAlmostEqual(abs(complex(row['response_re'],row['response_im'])),1)


if __name__=='__main__':unittest.main()
