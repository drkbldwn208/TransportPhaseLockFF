"""PDH helper: physical units, phase-only updates, and RFDC channel isolation."""
import math
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pdh_tones as pdh


class GPIO:
    def __init__(self, values=None):
        self.values = values or {}
        self.writes = []
    def read(self, address):
        return self.values.get(address, 0)
    def write(self, address, value):
        self.writes.append((address,value))
        self.values[address] = value


class PDHHelper(unittest.TestCase):
    def setUp(self):
        self.constants = SimpleNamespace(EVNT_SRC_IMMEDIATE=0, MIXER_TYPE_FINE=2,
            MIXER_TYPE_COARSE=1, MIXER_MODE_C2R=2, MIXER_MODE_R2R=4,
            COARSE_MIX_BYPASS=16, MIXER_SCALE_1P0=1, EVENT_MIXER=1)
        context = patch.dict(sys.modules, xrfdc=self.constants)
        context.start(); self.addCleanup(context.stop)
        block = lambda: SimpleNamespace(MixerSettings={'Freq':77.0}, NyquistZone=2,
            InterpolationFactor=4, ResetNCOPhase=Mock(), UpdateEvent=Mock())
        tiles = [SimpleNamespace(blocks=[block() for _ in range(4)]) for _ in range(2)]
        tiles[0].blocks[2].InterpolationFactor=2
        self.ol = SimpleNamespace(pdh_version=GPIO({0:pdh.FEATURE_VERSION}),
            pdh_control=GPIO({0:0,8:128}), pdh_amplitudes=GPIO(),
            usp_rf_data_converter_0=SimpleNamespace(dac_tiles=tiles),
            ip_dict={'usp_rf_data_converter_0':{'parameters':{
                'DAC_Data_Width12':14,'DAC_Interpolation_Mode12':4,
                'DAC_Data_Width02':8,'DAC_Interpolation_Mode02':2,
                'DAC0_Sampling_Rate':3.93216,'DAC1_Sampling_Rate':6.88128}}})
        original = self.ol.pdh_control.write
        def acknowledge(address, value):
            original(address,value)
            self.ol.pdh_control.values[8]=128|(value&7)
        self.ol.pdh_control.write=acknowledge

    def test_configure_only_two_requested_channels(self):
        result=pdh.configure(self.ol,carrier_amplitude=.6,sideband_amplitude=.15,
                             reference_amplitude=.4,reference_phase_deg=90)
        self.assertEqual(result['carrier_hz'],1.2e9)
        self.assertEqual(result['sideband_hz'],60e6)
        self.assertAlmostEqual(result['reference_phase_deg'],90)
        tiles=self.ol.usp_rf_data_converter_0.dac_tiles
        self.assertEqual(tiles[1].blocks[2].MixerSettings['Freq'],630)
        self.assertEqual(tiles[0].blocks[2].MixerSettings['CoarseMixFreq'],16)
        for tile in tiles:
            for index in (0,1,3):
                self.assertEqual(tile.blocks[index].MixerSettings,{'Freq':77.0})
                tile.blocks[index].UpdateEvent.assert_not_called()

    def test_phase_change_preserves_amplitudes_and_nco_phase(self):
        pdh.configure(self.ol,carrier_amplitude=.5,sideband_amplitude=.1,reference_amplitude=.5)
        source=self.ol.usp_rf_data_converter_0.dac_tiles[1].blocks[2]
        source.ResetNCOPhase.reset_mock(); source.UpdateEvent.reset_mock()
        previous=self.ol.pdh_amplitudes.read(0)
        for phase in (37,179,-92,720):
            result=pdh.set_reference_phase(self.ol,phase)
            self.assertEqual(self.ol.pdh_amplitudes.read(0),previous)
            delta=(result['reference_phase_deg']-phase+180)%360-180
            self.assertLess(abs(delta),.004)
            self.assertLess(abs(result['reference_amplitude']-.5),.0001)
        source.ResetNCOPhase.assert_not_called(); source.UpdateEvent.assert_not_called()

    def test_bad_amplitudes_rejected_before_any_writes(self):
        for carrier,sideband in ((.8,.3),(-.1,.2),(float('nan'),.1)):
            with self.assertRaises(ValueError):
                pdh.configure(self.ol,carrier_amplitude=carrier,sideband_amplitude=sideband)
        self.assertEqual(self.ol.pdh_control.writes,[])

    def test_default_ratio_and_explicit_override(self):
        pdh.configure(self.ol)
        self.assertEqual(self.ol.pdh_amplitudes.read(0),0)
        result=pdh.set_levels(self.ol)
        self.assertAlmostEqual(result['carrier_amplitude'],.55,places=4)
        self.assertLess(abs(result['sideband_amplitude']/result['carrier_amplitude']-pdh.DEFAULT_SIDEBAND_RATIO),.0001)
        result=pdh.set_levels(self.ol,carrier_amplitude=.2,sideband_amplitude=0)
        self.assertEqual(result['sideband_amplitude'],0)

    def test_mute_and_fault_reporting(self):
        pdh.configure(self.ol,carrier_amplitude=.5)
        result=pdh.stop(self.ol)
        self.assertFalse(result['sum_enabled']); self.assertFalse(result['reference_enabled'])
        self.ol.pdh_control.values[8]|=16
        with self.assertRaisesRegex(RuntimeError,'sticky fault'):
            pdh.set_levels(self.ol,carrier_amplitude=.5,sideband_amplitude=0,reference_amplitude=.5)


if __name__=='__main__':
    unittest.main()
