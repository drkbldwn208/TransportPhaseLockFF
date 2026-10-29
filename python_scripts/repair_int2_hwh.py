"""Repair the 2026-10-28 INT2 HWH; no FPGA download or register writes.

The bitstream has ILA slots 0/5 tied to zero. Its HWH incorrectly connects
those monitor inputs to each other. Remove only that unused debug metadata.
The hashes restrict this repair to the verified release, not arbitrary designs.
"""
from pathlib import Path
import hashlib
import io
import xml.etree.ElementTree as ET

ORIGINAL_SHA256 = 'bb4a1e4c8ad79c2b97f7d999844d1d82c8359a6b6a66d271b306b840b9328878'
REPAIRED_SHA256 = '5f130cfe0e594110bb8ea1677a9fa80174caa42bdc8506ca8a4c4fcf07f6e667'


def corrected_hwh(data):
    """Return corrected XML bytes; accept an already-repaired file unchanged."""
    digest = hashlib.sha256(data).hexdigest()
    if digest == REPAIRED_SHA256:
        return data
    if digest != ORIGINAL_SHA256:
        raise ValueError('This is not the affected INT2 HWH; leaving it unchanged.')
    tree = ET.ElementTree(ET.fromstring(data))
    ila = tree.find(".//MODULE[@INSTANCE='system_ila_0']")
    for slot in (0, 5):
        bus = f'SLOT_{slot}_AXIS'
        ila.find(f"./BUSINTERFACES/BUSINTERFACE[@NAME='{bus}']").set('BUSNAME', '__NOC__')
        for signal in ('tdata', 'tvalid'):
            port = ila.find(f"./PORTS/PORT[@NAME='{bus}_{signal}']")
            port.attrib.pop('SIGNAME', None)
            for connections in port.findall('CONNECTIONS'):
                port.remove(connections)
    output = io.BytesIO()
    tree.write(output, encoding='utf-8', xml_declaration=True)
    result = output.getvalue()
    if hashlib.sha256(result).hexdigest() != REPAIRED_SHA256:
        raise RuntimeError('Unexpected XML serialization; no file has been changed.')
    return result


def repair_hwh(path):
    """Back up and atomically replace this HWH only; safe to call twice."""
    path = Path(path)
    original = path.read_bytes()
    repaired = corrected_hwh(original)
    if repaired == original:
        return 'HWH already repaired.'
    backup = path.with_suffix('.hwh.before_int2_fix')
    if backup.exists() and backup.read_bytes() != original:
        raise ValueError(f'Unexpected backup already exists: {backup}')
    if not backup.exists():
        backup.write_bytes(original)
    temporary = path.with_suffix('.hwh.tmp')
    temporary.write_bytes(repaired)
    temporary.replace(path)
    return f'Repaired {path}; original saved as {backup.name}.'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hwh', type=Path)
    print(repair_hwh(parser.parse_args().hwh))
