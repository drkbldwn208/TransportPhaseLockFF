"""Reproduce INT2's PYNQ failure and verify its metadata-only repair.

Run with Python 3.10, pynqmetadata==0.1.5, pydantic<2 and IPython installed.
Uses the actual release HWH and generated RTL, not a mocked PYNQ parser.
"""
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET
from pynqmetadata.frontends import Metadata
from pynqmetadata.errors import WrongPolarityConnection

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python_scripts'))
from repair_int2_hwh import corrected_hwh, repair_hwh

source = ROOT / 'TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh'
original = source.read_bytes()
try:
    Metadata(input=source)
except WrongPolarityConnection as exc:
    assert 'SLOT_5_AXIS' in str(exc) and 'SLOT_0_AXIS' in str(exc)
    print('PASS: reproduced the reported WrongPolarityConnection')
else:
    raise AssertionError('Expected the original release metadata fault')

fixed = corrected_hwh(original)
assert corrected_hwh(fixed) == fixed
try:
    corrected_hwh(original + b' ')
except ValueError:
    pass
else:
    raise AssertionError('Unexpected HWH was accepted')

# Every element outside the ILA is identical, including all addresses, GPIOs,
# clocks, RFDC settings and DMA connections. Inside ILA, exactly six edits.
before, after = ET.fromstring(original), ET.fromstring(fixed)
expected = ET.fromstring(original)
ila = expected.find(".//MODULE[@INSTANCE='system_ila_0']")
for slot in (0, 5):
    ila.find(f"./BUSINTERFACES/BUSINTERFACE[@NAME='SLOT_{slot}_AXIS']").set('BUSNAME', '__NOC__')
    for signal in ('tdata', 'tvalid'):
        port = ila.find(f"./PORTS/PORT[@NAME='SLOT_{slot}_AXIS_{signal}']")
        port.attrib.pop('SIGNAME')
        port.remove(port.find('CONNECTIONS'))
assert ET.tostring(expected) == ET.tostring(after)

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'TransportPhaseLockFF.hwh'
    path.write_bytes(original)
    repair_hwh(path)
    assert path.read_bytes() == fixed
    assert path.with_suffix('.hwh.before_int2_fix').read_bytes() == original
    repair_hwh(path)
    metadata = Metadata(input=path)
    assert len(metadata.blocks) == 153
    for name in ('intensity_dma', 'axi_dma_4', 'pll_control', 'pll2_control'):
        assert name in metadata.blocks
    print(f'PASS: repaired metadata parses all {len(metadata.blocks)} blocks; repeat repair preserves backup')

# Check the explanation against the physical generated wrapper, not just HWH.
import re
rtl = (ROOT / 'TransportPhaseLockFF.gen/sources_1/bd/design_1/synth/design_1.v').read_text()
ila_rtl = re.search(r'\bsystem_ila_0\s*\((.*?)\);', rtl, re.S).group(1)
for slot in (0, 1, 5):
    for signal in ('tdata', 'tvalid'):
        value = re.search(rf'\.SLOT_{slot}_AXIS_{signal}\(([^)]+)\)', ila_rtl).group(1)
        assert set(re.findall(r"1'b([01])", value)) == {'0'}, value
        assert re.fullmatch(r"[{},\s]*(?:1'b0[{},\s]*)+", value), value
for signal in ('tdata', 'tvalid'):
    assert f'.SLOT_4_AXIS_{signal}(axis_tlast_gen_3_m_axis_{signal.upper()})' in ila_rtl
print('PASS: slots 0/1/5 physically tied to zero; slot 4 retains packetized calibration phase')
