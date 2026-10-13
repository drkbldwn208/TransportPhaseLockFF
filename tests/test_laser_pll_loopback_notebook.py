"""Execute every A8 loopback notebook cell using a known-delay register model."""
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('MPLCONFIGDIR','/tmp/laser_loopback_matplotlib')
import matplotlib
matplotlib.use('Agg')
from test_laser_pll_loopback import Loopback
import laser_pll_loopback as lb

ROOT=Path(__file__).resolve().parents[1]
fixture=Loopback(); fixture.setUp(); ol=fixture.ol
# The fixture implements register sums, not an alternate sweep algorithm.
ol.usp_rf_data_converter_0=SimpleNamespace(dac_tiles=[SimpleNamespace(blocks=[None,SimpleNamespace(
    MixerSettings={'Freq':90.0},UpdateEvent=lambda _:None)])])
ol.axi_gpio_12=SimpleNamespace(channel1=SimpleNamespace(write=lambda *a,**k:None))
output=Path('/tmp/laser_pll_loopback_notebook_test'); output.mkdir(exist_ok=True)
cells=json.loads((ROOT/'python_scripts/laser_pll_loopback.ipynb').read_text())['cells']
namespace={}
old=Path.cwd()
try:
    os.chdir(output)
    fake_pynq=SimpleNamespace(Overlay=lambda _:ol)
    fake_xrfdc=SimpleNamespace(EVENT_MIXER=1)
    with patch.dict(sys.modules,pynq=fake_pynq,xrfdc=fake_xrfdc), \
         patch('importlib.reload',lambda module:module), \
         patch.object(lb,'setup',return_value={'mode':'mixer'}), \
         contextlib.redirect_stdout(io.StringIO()):
        for index,cell in enumerate(cells):
            if cell['cell_type']=='code':
                exec(compile(''.join(cell['source']),f'loopback notebook cell {index}','exec'),namespace)
    assert len(namespace['rows'])==61
    assert abs(namespace['delay']['delay_s']-fixture.delay_s)<1e-12
    path=namespace['csv_path']
    assert path.exists() and path.with_suffix('.png').exists() and path.with_suffix('.json').exists()
    assert path.with_name(path.stem+'_blocks.csv').exists()
    assert ol.pll_control.read(0)&1==0
    print(f'PASS: all loopback notebook cells; known {fixture.delay_s*1e9:g} ns delay; CSV/JSON/plot outputs in {output}')
finally:
    os.chdir(old)
    fixture.doCleanups()
