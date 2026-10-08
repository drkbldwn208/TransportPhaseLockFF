"""Execute every bring-up code cell against GPIO/RFDC mocks, never board hardware."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use('Agg')

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('laser_pll',ROOT/'python_scripts/laser_pll.py')
pll=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pll)


class GPIO:
    def __init__(self):
        self.values={0:0,8:0}
    def read(self,address):
        return self.values[address]
    def write(self,address,value):
        self.values[address]=value


def run():
    ol=SimpleNamespace(pll_frequency=GPIO(),pll_control=GPIO(),pll_status=GPIO(),
                       pll_acquisition=GPIO(),pll_acquisition_status=GPIO())
    hwh=ROOT/'TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh'
    rfdc=next(m for m in ET.parse(hwh).iter('MODULE') if m.get('INSTANCE')=='usp_rf_data_converter_0')
    parameters={p.get('NAME'):p.get('VALUE') for p in rfdc.iter('PARAMETER')}
    ol.ip_dict={'usp_rf_data_converter_0':{'parameters':parameters}}
    dac=SimpleNamespace(MixerSettings={},ResetNCOPhase=lambda:None,UpdateEvent=lambda _:None)
    ol.usp_rf_data_converter_0=SimpleNamespace(dac_tiles=[None,SimpleNamespace(blocks=[None,dac])])
    # Emulate already-qualified/settled hardware, not its dynamics (tested in RTL).
    def read_status(address):
        if address==8: return 0
        return ((ol.pll_frequency.read(8)>>16)&1)<<22 | (ol.pll_control.read(0)&1)<<18 | 1<<19
    def read_acquisition(address):
        if address==8: return 0xA4010000 | 1024 | 417
        config=ol.pll_acquisition.read(0)
        return (4 if config&4 else config&3) | 0xe0
    ol.pll_status.read=read_status
    ol.pll_acquisition_status.read=read_acquisition
    xrfdc=SimpleNamespace(EVNT_SRC_IMMEDIATE=0,MIXER_TYPE_FINE=2,
                         MIXER_MODE_C2R=3,MIXER_SCALE_1P0=1,EVENT_MIXER=1)
    namespace={}
    cells=json.loads((ROOT/'python_scripts/laser_pll_bringup.ipynb').read_text())['cells']
    with patch.dict(sys.modules,laser_pll=pll,pynq=SimpleNamespace(Overlay=lambda _:ol),xrfdc=xrfdc), \
         patch.object(pll.time,'sleep',lambda _:None), contextlib.redirect_stdout(io.StringIO()):
        for index,cell in enumerate(cells):
            if cell['cell_type']=='code':
                source=''.join(cell['source'])
                exec(compile(source,f'notebook cell {index}','exec'),namespace)
    assert not ol.pll_control.read(0)&1, 'Notebook must end muted'
    assert dac.MixerSettings['Freq']==0 and dac.MixerSettings['PhaseOffset']==0
    print(f'PASS: {sum(c["cell_type"]=="code" for c in cells)} notebook code cells with generated HWH and mocked hardware; ends muted')


if __name__=='__main__': run()
