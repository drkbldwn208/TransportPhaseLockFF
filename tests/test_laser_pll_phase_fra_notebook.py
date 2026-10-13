"""Run the delivered notebook against modeled registers/RFDC with real helpers.

Check both measurements, a 403 ns RF path, startup versus helper-only refresh,
and saved phasors/metadata/figures. No hardware or physical laser is modeled.
"""
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
os.environ.setdefault('MPLCONFIGDIR', '/tmp/phase_fra_mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from test_laser_pll_phase_fra import PhaseFRA

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=Path('/tmp/laser_pll_phase_fra_notebook_test');OUTPUT.mkdir(exist_ok=True)
(OUTPUT/'laser_pll_R7.py').write_bytes((ROOT/'python_scripts/laser_pll.py').read_bytes())
sys.path.insert(0,str(OUTPUT))
clock_file=OUTPUT/'test_lmk.txt';clock_file.write_text('Register 0\t0x000012\nRegister 1\t0x000034\n')
cells=json.loads((ROOT/'python_scripts/laser_pll_phase_fra.ipynb').read_text())['cells']


def run_notebook(mode):
    fixture=PhaseFRA();fixture.setUp();ol=fixture.ol
    rf=ol.usp_rf_data_converter_0
    rf.dac_tiles[0]=SimpleNamespace(blocks=[])
    for tile in [rf.adc_tiles[0],*rf.dac_tiles]:
        tile.StartUp=Mock();tile.PLLLockStatus=1
    fake_pynq=SimpleNamespace(Overlay=Mock(return_value=ol))
    clock_api=SimpleNamespace(lmk_devices=[{'compatible':'lmk'}],lmx_devices=[{}],_Config={'lmk':{}},
                              _find_devices=Mock(),_read_tics_output=Mock())
    fake_xrfclk=SimpleNamespace(xrfclk=clock_api,set_ref_clks=Mock())
    ns={};old=Path.cwd()
    try:
        os.chdir(OUTPUT)
        with patch.dict(sys.modules,pynq=fake_pynq,xrfclk=fake_xrfclk),contextlib.redirect_stdout(io.StringIO()):
            for index,cell in enumerate(cells):
                if cell['cell_type']!='code':continue
                source=''.join(cell['source'])
                source=source.replace('initialize_hardware = False','initialize_hardware = True')
                source=source.replace('/home/xilinx/jupyter_notebooks/LMK_245_76_ExtRef10.txt',str(clock_file))
                source=source.replace("measurement_mode = 'closed'",f"measurement_mode = '{mode}'")
                exec(compile(source,f'phase FRA notebook cell {index}','exec'),ns)
            assert len(ns['rows'])==61
            path=ns['csv_path'];assert path.exists() and path.with_suffix('.png').exists()
            assert path.with_name(path.stem+'_blocks.csv').exists()
            metadata=json.loads(path.with_suffix('.json').read_text())
            assert metadata['mode']==mode and metadata['feature_version']=='0x52463701'
            assert ol.pll_fra_tone.read(0x18)==0 and ol.pll_fra.read(0)==0
            assert ol.pll_control.read(0)&1
            assert ns['fra'].laser_pll is ns['laser_pll'] and ns['pf'].laser_pll is ns['laser_pll']
            assert ns['pf'].fra is ns['fra'] and sys.modules['laser_pll'] is ns['laser_pll']
            if mode=='rf':
                assert abs(ns['delay_s']-fixture.delay_s)<1e-12
                assert ol.pll_rf_source.read(0)==8192
            else:
                assert all(r['loop_reliable'] for r in ns['rows'])
                assert not ol.pll_control.writes # preserve existing lock
            fake_pynq.Overlay.assert_called_once()
            fake_xrfclk.set_ref_clks.assert_called_once_with(lmk_freq=245.761,lmx_freq=491.52)
            assert clock_api._Config['lmk'][245.761]==[0x12,0x34]
            for tile in [rf.adc_tiles[0],*rf.dac_tiles]:tile.StartUp.assert_called_once()
            old_registers=(dict(ol.pll_control.values),dict(ol.pll_acquisition.values))
            exec(''.join(cells[1]['source']),ns) # default: Python-only refresh
            assert (ol.pll_control.values,ol.pll_acquisition.values)==old_registers
            assert fake_pynq.Overlay.call_count==fake_xrfclk.set_ref_clks.call_count==1
            ns['pf'].check_helpers(ol)
        print(f'PASS: {mode}, 61 points, helper refresh, state preservation, CSV/JSON/PNG, known phase response')
    finally:
        os.chdir(old);plt.close('all');fixture.doCleanups()


for mode in ('closed','rf'):run_notebook(mode)
print('PASS: complete R7 phase FRA notebook')
