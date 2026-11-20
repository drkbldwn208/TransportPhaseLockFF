"""Check that the PDH migration changes only the intended converter routing.

Compare against the saved pre-migration BD. Also inspect the generated HDL:
an AXIS-interface connection alone does not rule out a scalar pin override.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'build/PDH_DAC230_1200_60'


def peers(design, endpoint, kind='interface_nets'):
    key = 'interface_ports' if kind=='interface_nets' else 'ports'
    return sorted(p for net in design[kind].values() if endpoint in net[key]
                  for p in net[key] if p!=endpoint)


def main():
    old = json.loads((OUT/'backup/design_1.bd').read_text())['design']
    new = json.loads((ROOT/'TransportPhaseLockFF.srcs/sources_1/bd/design_1/design_1.bd').read_text())['design']
    a = old['components']['usp_rf_data_converter_0']['parameters']
    b = new['components']['usp_rf_data_converter_0']['parameters']
    changes = {k:(a.get(k), b.get(k)) for k in a.keys()|b.keys() if a.get(k)!=b.get(k)}
    assert all(k.startswith('DAC2_') or k=='DAC_Slice20_Enable' or
               (k.startswith('DAC_') and k.endswith('20')) for k in changes), changes
    assert new['addressing']==old['addressing'], 'An existing address map changed'
    expected = {'usp_rf_data_converter_0/s12_axis':['laser_pll_0/m_rf_axis'],
                'usp_rf_data_converter_0/s20_axis':['pdh_tones_0/m_sum'],
                'usp_rf_data_converter_0/s02_axis':['pdh_tones_0/m_ref']}
    for endpoint, sources in expected.items():
        assert peers(new,endpoint)==sources, (endpoint,peers(new,endpoint))
    # All other preexisting RFDC streams, external ports and components remain.
    for net in old['interface_nets'].values():
        for endpoint in net['interface_ports']:
            if endpoint.startswith('usp_rf_data_converter_0/') and endpoint not in expected:
                assert peers(new,endpoint)==peers(old,endpoint), endpoint
    for name, component in old['components'].items():
        if name not in ('usp_rf_data_converter_0','pdh_tones_0'):
            assert new['components'][name].get('parameters')==component.get('parameters'), name
    for endpoint in ('usp_rf_data_converter_0/s2_axis_aclk','pdh_tones_0/clk'):
        assert 'usp_rf_data_converter_0/clk_adc1' in peers(new,endpoint,'nets')
    assert peers(new,'usp_rf_data_converter_0/vout20')==['vout20']
    rtl = (ROOT/'TransportPhaseLockFF.gen/sources_1/bd/design_1/synth/design_1.v').read_text()
    rf = re.search(r'\busp_rf_data_converter_0\s*\((.*?)\);',rtl,re.S).group(1)
    pdh = re.search(r'\bpdh_tones_0\s*\((.*?)\);',rtl,re.S).group(1)
    pin = lambda instance, name: re.search(r'\.'+name+r'\(([^)]+)\)',instance).group(1).strip()
    for converter, generator in (('s20_axis','m_sum'),('s02_axis','m_ref')):
        for signal in ('tdata','tvalid','tready'):
            assert pin(rf,converter+'_'+signal)==pin(pdh,generator+'_'+signal), (converter,signal)
    for mapping in new['interface_ports']['vout20']['port_maps'].values():
        assert mapping['physical_name'] in rtl
    result = dict(status='pass', unchanged_existing_tile_settings=True,
                  rfdc_parameter_changes=changes, streams=expected,
                  existing_addresses_unchanged=True, scalar_routing_checked=True)
    (OUT/'connectivity_check.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: DAC230 real stream, distributed clock, external output; existing converters/feedback/address map preserved')


if __name__=='__main__':
    main()
