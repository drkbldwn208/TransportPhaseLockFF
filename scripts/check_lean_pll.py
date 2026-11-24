"""Compare cleanup against the saved design, including physical signal wiring.

The oldest 2:1 transport PLL and intensity/PDH paths must keep their settings,
connections and PS addresses. Only diagnostic cells and AXI slot numbers change.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/PLL_LEAN'
REMOVED = {'system_ila_0', 'axi_dma_3', 'pll2_iq_dma', 'pll_iq_fifo',
           'pll2_iq_fifo', 'pll_monitor', 'pll2_monitor', 'pll_rf_source'}
for prefix in ('pll', 'pll2'):
    REMOVED.update(prefix + '_' + suffix for suffix in
                   ('fra', 'fra_window', 'fra_tone', 'fra_error', 'fra_drive',
                    'fra_counts', 'fra_extrema', 'fra_samples'))
INTERCONNECTS = {'axi_interconnect_0', 'pll_extension_axi', 'smartconnect_0'}
PLL = {'laser_pll_0', 'laser_pll_1'}


def relevant(endpoint):
    cell, _, pin = endpoint.partition('/')
    if cell in REMOVED or cell in INTERCONNECTS:
        return False
    if cell in PLL and (pin.startswith(('fra_', 's_fra', 'm_fra', 'monitor_', 'm_monitor',
                                        'rf_source', 'm_rf'))):
        return False
    return True


def main():
    old = json.loads((OUT / 'backup/design_1.bd').read_text())['design']
    new = json.loads((ROOT / 'TransportPhaseLockFF.srcs/sources_1/bd/design_1/design_1.bd').read_text())['design']
    assert not REMOVED.intersection(new['components'])
    assert set(old['components']) - set(new['components']) == REMOVED
    for name, component in old['components'].items():
        if name not in REMOVED | INTERCONNECTS | PLL:
            assert component.get('parameters') == new['components'][name].get('parameters'), name
    for name in PLL:
        assert new['components'][name]['parameters']['STAGE3_RANGE_SHIFT'] == old['components'][name]['parameters']['STAGE3_RANGE_SHIFT']
    checked = 0
    for kind, key in (('nets', 'ports'), ('interface_nets', 'interface_ports')):
        new_nets = [set(net[key]) for net in new[kind].values()]
        for name, net in old[kind].items():
            survivors = {p for p in net[key] if relevant(p)}
            if len(survivors) >= 2:
                assert any(survivors <= candidate for candidate in new_nets), (name, survivors)
                checked += 1
    old_addresses = old['addressing']['/zynq_ultra_ps_e_0']['address_spaces']['Data']['segments']
    new_addresses = new['addressing']['/zynq_ultra_ps_e_0']['address_spaces']['Data']['segments']
    for name, segment in old_addresses.items():
        cell = segment['address_block'].strip('/').split('/')[0]
        if cell not in REMOVED:
            assert new_addresses[name] == segment, (name, segment, new_addresses.get(name))
    # A moved AXI slot must retain its old clock/reset source as well as address.
    def clock_reset(design):
        result = {}
        sources = {'zynq_ultra_ps_e_0/pl_clk0', 'usp_rf_data_converter_0/clk_adc1',
                   'rst_ps8_0_99M/peripheral_aresetn', 'proc_sys_reset_0/peripheral_aresetn'}
        for net in design['interface_nets'].values():
            ports = net['interface_ports']
            for port in ports:
                block, _, pin = port.partition('/')
                if block not in INTERCONNECTS or not pin.startswith('M') or block == 'smartconnect_0':
                    continue
                destination = next(p for p in ports if p != port)
                if destination.split('/')[0] in REMOVED:
                    continue
                for suffix in ('ACLK', 'ARESETN'):
                    clock_pin = block + '/' + pin[:3] + '_' + suffix
                    drivers = {p for n in design['nets'].values() if clock_pin in n['ports']
                               for p in n['ports'] if p in sources}
                    assert len(drivers) == 1, (clock_pin, drivers)
                    result[destination, suffix] = drivers
        return result
    assert clock_reset(old) == clock_reset(new), 'Peripheral AXI clock/reset domain changed'
    # Check generated wiring too: the inactive DAC229/2 must remain zero/invalid.
    import re
    rtl = (ROOT / 'TransportPhaseLockFF.gen/sources_1/bd/design_1/synth/design_1.v').read_text()
    rf = re.search(r'\busp_rf_data_converter_0\s*\((.*?)\);', rtl, re.S).group(1)
    assert '.s12_axis_tdata(pll_unused_dac_zero_dout)' in rf
    assert '.s12_axis_tvalid(xlconstant_2_dout[0])' in rf
    assert not re.search(r'\bsystem_ila_0\s*\(', rtl)
    result = dict(status='pass', removed_cells=sorted(REMOVED),
                  preserved_signal_nets=checked, surviving_addresses_unchanged=True,
                  all_converter_settings_unchanged=True)
    (OUT / 'connectivity_check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'PASS: {checked} preserved signal nets; original 2:1 transport, intensity, PDH and converter settings/addresses unchanged')


if __name__ == '__main__':
    main()
