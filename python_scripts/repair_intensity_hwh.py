"""Correct redundant ILA connections in the IS03 Vivado HWH metadata only.

Vivado emits both the real CORDIC driver and a monitor-to-monitor connection
for ILA slots 0/5. PYNQ rejects the latter as two inputs connected together.
Verify the generated hardware wrapper before retaining only the actual driver.
This does not change the bitstream, register map, or any functional connection.
"""
from pathlib import Path
import io
import re
import xml.etree.ElementTree as ET


def _instance_ports(rtl, instance):
    match = re.search(rf'\b{re.escape(instance)}\s*\((.*?)\);', rtl, re.S)
    if match is None:
        raise ValueError(f'Generated RTL has no {instance} instance.')
    return dict(re.findall(r'\.([A-Za-z0-9_]+)\s*\(\s*([^()]*)\s*\)', match.group(1)))


def corrected_hwh(data, generated_rtl):
    """Return verified metadata; leave an already-correct file byte-identical.

    Both arguments are file contents (HWH bytes and generated Verilog text).
    Refuse unexpected drivers rather than making assumptions about a new design.
    """
    tree = ET.ElementTree(ET.fromstring(data))
    for instance in ('intensity_linearized_0', 'intensity_shot_dma'):
        if tree.find(f".//MODULE[@INSTANCE='{instance}']") is None:
            raise ValueError(f'Expected IS03 block {instance}; HWH left unchanged.')
    ila = tree.find(".//MODULE[@INSTANCE='system_ila_0']")
    cordic = tree.find(".//MODULE[@INSTANCE='cordic_0']")
    if ila is None or cordic is None:
        raise ValueError('Required ILA/CORDIC block is missing.')
    ila_ports = _instance_ports(generated_rtl, 'system_ila_0')
    cordic_ports = _instance_ports(generated_rtl, 'cordic_0')
    source_bus = cordic.find("./BUSINTERFACES/BUSINTERFACE[@NAME='M_AXIS_DOUT']")
    if source_bus is None or source_bus.get('BUSNAME') != 'cordic_0_M_AXIS_DOUT':
        raise ValueError('Unexpected CORDIC interface; HWH left unchanged.')
    changed = False
    for slot in (0, 5):
        bus_name = f'SLOT_{slot}_AXIS'
        bus = ila.find(f"./BUSINTERFACES/BUSINTERFACE[@NAME='{bus_name}']")
        if bus is None or bus.get('BUSNAME') != source_bus.get('BUSNAME'):
            raise ValueError(f'{bus_name} does not monitor the verified CORDIC bus.')
        for suffix in ('tdata', 'tvalid'):
            name = f'{bus_name}_{suffix}'
            source_port = f'm_axis_dout_{suffix}'
            net = f'cordic_0_{source_port}'
            if ila_ports.get(name, '').strip() != net or cordic_ports.get(source_port, '').strip() != net:
                raise ValueError(f'Generated RTL does not connect {name} to {net}.')
            port = ila.find(f"./PORTS/PORT[@NAME='{name}']")
            driver = cordic.find(f"./PORTS/PORT[@NAME='{source_port}']")
            if port is None or driver is None or port.get('DIR') != 'I' or driver.get('DIR') != 'O':
                raise ValueError(f'Unexpected port direction or missing port for {name}.')
            if driver.get('SIGNAME') != net:
                raise ValueError(f'Unexpected CORDIC source net for {name}.')
            real_connection = ('cordic_0', source_port)
            stale_connection = ('system_ila_0', f'SLOT_{5 if slot == 0 else 0}_AXIS_{suffix}')
            connections = [(c.get('INSTANCE'), c.get('PORT')) for c in port.iter('CONNECTION')]
            if real_connection not in connections or any(c not in (real_connection, stale_connection) for c in connections):
                raise ValueError(f'Unexpected HWH connection for {name}; left unchanged.')
            if port.get('SIGNAME') == net and connections == [real_connection]:
                continue
            if port.get('SIGNAME') not in (net, f'system_ila_0_SLOT_0_AXIS_{suffix}'):
                raise ValueError(f'Unexpected ILA net name for {name}; left unchanged.')
            port.set('SIGNAME', net)
            for group in port.findall('CONNECTIONS'):
                port.remove(group)
            ET.SubElement(ET.SubElement(port, 'CONNECTIONS'), 'CONNECTION',
                          INSTANCE='cordic_0', PORT=source_port)
            changed = True
    if not changed:
        return data
    output = io.BytesIO()
    tree.write(output, encoding='utf-8', xml_declaration=True)
    return output.getvalue()


def repair_hwh(path, generated_rtl_path):
    """Back up original metadata and atomically replace only the given HWH."""
    path = Path(path)
    original = path.read_bytes()
    repaired = corrected_hwh(original, Path(generated_rtl_path).read_text())
    if repaired == original:
        return f'Already correct: {path}'
    # The backup deliberately does not end in .hwh: overlay monitors must never
    # mistake the defective original for the most recent hardware description.
    backup = path.with_suffix('.hwh.before_is03_fix')
    if backup.exists() and backup.read_bytes() != original:
        import hashlib
        backup = path.with_suffix('.hwh.before_is03_fix.' + hashlib.sha256(original).hexdigest()[:12])
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
    parser.add_argument('generated_rtl', type=Path)
    args = parser.parse_args()
    print(repair_hwh(args.hwh, args.generated_rtl))
