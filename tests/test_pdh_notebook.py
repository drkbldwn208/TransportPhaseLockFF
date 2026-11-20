"""Execute the PDH operating sequence with modeled RFDC registers.

Checks the delivered notebook's imports/calls against its real helper. Does not
model analog spectral purity, clock locking, or physically restart a converter.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from test_pdh_helper import PDHHelper

root = Path(__file__).resolve().parents[1]
fixture = PDHHelper()
fixture.setUp()
try:
    ol = fixture.ol
    tile = ol.usp_rf_data_converter_0.dac_tiles[2]
    tile.PLLLockStatus = 1
    tile.PLLConfig = {'SampleRate':6.88128, 'RefClkFreq':491.52}
    tile.blocks[0].BlockStatus = {'SamplingFreq':6.88128, 'IsFIFOFlagsAsserted':0}
    overlay = Mock(return_value=ol)
    namespace = {'ol':ol}
    with patch.dict(sys.modules, pynq=SimpleNamespace(Overlay=overlay)):
        notebook = json.loads((root/'python_scripts/pdh_tones.ipynb').read_text())
        for index, cell in enumerate(notebook['cells']):
            if cell['cell_type']=='code':
                exec(compile(''.join(cell['source']), f'PDH notebook cell {index}', 'exec'), namespace)
    overlay.assert_not_called()  # Attach already bound; never download anything.
    state = namespace['pdh'].status(ol)
    assert not state['sum_enabled'] and not state['reference_enabled']
    assert not state['fault']
    print('PASS: complete PDH2 notebook, matching helper, levels/phase/diagnostics/mute')
finally:
    fixture.doCleanups()
