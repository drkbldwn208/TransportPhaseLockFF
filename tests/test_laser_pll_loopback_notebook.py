"""Execute the complete notebook with real helper reloads and modeled RFDC/registers.

Exercise mixer/direct fixtures, signed mV conversion, startup and Python-only
refresh. The register model supplies a known gain and 403 ns propagation delay;
this is not a physical board test.
"""
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
os.environ.setdefault('MPLCONFIGDIR','/tmp/laser_loopback_matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from test_laser_pll_loopback import Loopback

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path('/tmp/laser_pll_loopback_notebook_test')
OUTPUT.mkdir(exist_ok=True)
# The release contains this same generated, versioned copy of the A8 control helper.
(OUTPUT/'laser_pll_R8.py').write_bytes((ROOT/'python_scripts/laser_pll.py').read_bytes())
sys.path.insert(0,str(OUTPUT))
clock_file = OUTPUT/'test_lmk.txt'
clock_file.write_text('Register 0\t0x000012\nRegister 1\t0x000034\n')
cells = json.loads((ROOT/'python_scripts/laser_pll_loopback.ipynb').read_text())['cells']


def run_notebook(mode):
    fixture = Loopback(); fixture.setUp(); ol = fixture.ol
    # Use the real receiver_settings() and setup(), instead of replacing notebook logic.
    fixture.settings.stop()
    block = lambda frequency: SimpleNamespace(MixerSettings={'Freq':frequency},
                                              UpdateEvent=Mock(),ResetNCOPhase=Mock())
    tile = lambda blocks: SimpleNamespace(blocks=blocks,StartUp=Mock(),PLLLockStatus=1)
    rfdc = SimpleNamespace(
        adc_tiles=[tile([None,None,None,block(0.0)])],
        dac_tiles=[tile([None,block(90.0)]),tile([None,block(0.0)])],
        IPStatus={'ADCTileStatus':[{'TileState':15}],
                  'DACTileStatus':[{'TileState':15},{'TileState':15}]})
    ol.usp_rf_data_converter_0 = rfdc
    ol.ip_dict = {'usp_rf_data_converter_0':{'parameters':{
        'ADC_Decimation_Mode03':'1','ADC_Data_Type03':'0','DAC_Interpolation_Mode11':'4'}}}
    # Acknowledge frequency-word commits, as the receiver does in hardware.
    ol.pll_status = SimpleNamespace(read=lambda _: ((ol.pll_frequency.read(8)>>16)&1)<<22)
    lo_word = [0]
    ol.axi_gpio_12 = SimpleNamespace(
        read=lambda _:lo_word[0],
        channel1=SimpleNamespace(write=lambda value,mask:lo_word.__setitem__(0,value&mask)))
    fake_pynq = SimpleNamespace(Overlay=Mock(return_value=ol))
    fake_xrfdc = SimpleNamespace(EVENT_MIXER=1,EVNT_SRC_IMMEDIATE=0,MIXER_TYPE_FINE=2,
                                 MIXER_MODE_C2R=2,MIXER_SCALE_1P0=1)
    clock_api = SimpleNamespace(lmk_devices=[],lmx_devices=[],_Config={'lmk':{}},
                                 _read_tics_output=Mock())
    def find_devices():
        clock_api.lmk_devices=[{'compatible':'lmk'}]
        clock_api.lmx_devices=[{'compatible':'lmx'}]
    clock_api._find_devices = Mock(side_effect=find_devices)
    fake_xrfclk = SimpleNamespace(xrfclk=clock_api,set_ref_clks=Mock())
    namespace = {}
    old = Path.cwd()
    try:
        os.chdir(OUTPUT)
        with patch.dict(sys.modules,pynq=fake_pynq,xrfdc=fake_xrfdc,xrfclk=fake_xrfclk), \
             patch('builtins.input',side_effect=['-2','-12']) as meter, \
             contextlib.redirect_stdout(io.StringIO()):
            for index,cell in enumerate(cells):
                if cell['cell_type'] != 'code': continue
                source = ''.join(cell['source'])
                source = source.replace('/home/xilinx/jupyter_notebooks/LMK_245_76_ExtRef10.txt',str(clock_file))
                source = source.replace('mode = "mixer"',f'mode = "{mode}"')
                exec(compile(source,f'loopback notebook cell {index}','exec'),namespace)

            assert len(namespace['rows']) == 61
            assert abs(namespace['delay']['delay_s']-fixture.delay_s) < 1e-12
            path = namespace['csv_path']
            assert path.exists() and path.with_suffix('.png').exists() and path.with_suffix('.json').exists()
            assert path.with_name(path.stem+'_blocks.csv').exists()
            assert ol.pll_control.read(0)&1 == 0
            assert namespace['fra'].laser_pll is namespace['laser_pll']
            assert namespace['lb'].laser_pll is namespace['laser_pll']
            assert sys.modules['laser_pll'] is namespace['laser_pll']
            fake_pynq.Overlay.assert_called_once_with('/home/xilinx/Bitfiles/FreqLocksBranch/overlays/TransportPhaseLockFF.bit')
            fake_xrfclk.set_ref_clks.assert_called_once_with(lmk_freq=245.761,lmx_freq=491.52)
            assert clock_api._Config['lmk'][245.761] == [0x12,0x34]
            for t in (rfdc.adc_tiles[0],rfdc.dac_tiles[0],rfdc.dac_tiles[1]): t.StartUp.assert_called_once()
            metadata = json.loads(path.with_suffix('.json').read_text())
            if mode == 'mixer':
                assert meter.call_count == 2
                assert metadata['voltage_readings_mV'] == {'code_0':-2.0,'code_100':-12.0}
                limits = namespace['output_limits']
                assert abs(limits['volts_per_code']+.0001) < 1e-12
                assert abs(limits['offset_V']+.002) < 1e-12
                assert namespace['point']['predicted_peak_V']+.020 < .100
                assert namespace['setup_info']['output_limits'] == limits
            else:
                assert meter.call_count == 0
                assert namespace['output_limits'] is None
                assert rfdc.dac_tiles[1].blocks[1].MixerSettings['Freq'] == 90.0

            # Refresh the startup cell in the same kernel: no clocks, bit download or tile restarts.
            startup = ''.join(cells[1]['source']).replace('initialize_hardware = True','initialize_hardware = False')
            exec(compile(startup,'Python-only refresh','exec'),namespace)
            assert fake_pynq.Overlay.call_count == 1
            assert fake_xrfclk.set_ref_clks.call_count == 1
            for t in (rfdc.adc_tiles[0],rfdc.dac_tiles[0],rfdc.dac_tiles[1]): assert t.StartUp.call_count == 1
            namespace['lb'].check_helpers(ol)
        print(f'PASS: {mode} notebook, actual helper reloads, startup/refresh, 61-point sweep, '
              f'{fixture.delay_s*1e9:g} ns delay and CSV/JSON/PNG outputs')
    finally:
        os.chdir(old)
        plt.close('all')
        fixture.doCleanups()


for mode in ('mixer','rf'):
    run_notebook(mode)
print(f'PASS: all loopback notebook cells; outputs in {OUTPUT}')
