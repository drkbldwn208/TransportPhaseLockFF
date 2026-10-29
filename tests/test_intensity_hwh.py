"""Verify IS03 metadata repair using real generated RTL and PYNQ's parser.

Run with pynqmetadata 0.1.5 and pydantic<2 (local Python 3.10 environment).
No hardware registers or project sources are changed by this test.
"""
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET
from pynqmetadata.frontends import Metadata
from pynqmetadata.errors import WrongPolarityConnection

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python_scripts'))
from repair_intensity_hwh import corrected_hwh, repair_hwh

source = ROOT / 'TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh'
rtl_path = ROOT / 'TransportPhaseLockFF.gen/sources_1/bd/design_1/synth/design_1.v'
backup = source.with_suffix('.hwh.before_is03_fix')
original = (backup if backup.exists() else source).read_bytes()
rtl = rtl_path.read_text()
fixed = corrected_hwh(original, rtl)
assert fixed != original, 'Need the affected generated metadata or original backup.'
assert corrected_hwh(fixed, rtl) == fixed

# Exactly four ILA port records change; addresses, clocks, functional blocks,
# source fanout, and all other debug records remain semantically identical.
before, after = ET.fromstring(original), ET.fromstring(fixed)
for slot in (0, 5):
    for suffix in ('tdata', 'tvalid'):
        selector = f".//MODULE[@INSTANCE='system_ila_0']/PORTS/PORT[@NAME='SLOT_{slot}_AXIS_{suffix}']"
        left, right = before.find(selector), after.find(selector)
        left.attrib.clear(); left.attrib.update(right.attrib)
        for child in list(left):
            left.remove(child)
        for child in list(right):
            left.append(ET.fromstring(ET.tostring(child)))
        # Formatting whitespace is not hardware metadata.
        left.text = right.text
        left.tail = right.tail
assert ET.tostring(before) == ET.tostring(after)
try:
    corrected_hwh(original, rtl.replace('.SLOT_5_AXIS_tdata(cordic_0_m_axis_dout_tdata)',
                                       ".SLOT_5_AXIS_tdata(16'b0)"))
except ValueError:
    pass
else:
    raise AssertionError('Repair accepted mismatching physical RTL.')

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'TransportPhaseLockFF.hwh'
    path.write_bytes(original)
    try:
        Metadata(input=path)
    except WrongPolarityConnection as exc:
        assert 'SLOT_5_AXIS' in str(exc) and 'SLOT_0_AXIS' in str(exc)
    else:
        raise AssertionError('Expected the original metadata polarity fault.')
    repair_hwh(path, rtl_path)
    assert path.read_bytes() == fixed
    repair_hwh(path, rtl_path)
    assert path.with_suffix('.hwh.before_is03_fix').read_bytes() == original
    metadata = Metadata(input=path)
    for name in ('intensity_linearized_0', 'intensity_shot_dma', 'intensity_dma',
                 'axi_dma_4', 'pll_control', 'pll2_control'):
        assert name in metadata.blocks
    print(f'PASS: original fault reproduced; exactly four ILA port records repaired; '
          f'all {len(metadata.blocks)} blocks parse; RTL mismatch rejected; repair idempotent.')
