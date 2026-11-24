"""Check preserved feedback wiring, new PDH controls, photon DMA and generated RTL."""
from pathlib import Path
import json
import re

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/PDH_TUNABLE_PHOTON'
old=json.loads((OUT/'backup/design_1.bd').read_text())['design']
new=json.loads((ROOT/'TransportPhaseLockFF.srcs/sources_1/bd/design_1/design_1.bd').read_text())['design']
changed={'photon_counting','pdh_tones_0','smartconnect_0','intensity_servo_axi'}
for name,cell in old['components'].items():
    if name not in changed:
        assert new['components'][name].get('parameters')==cell.get('parameters'),name
old_addr=old['addressing']['/zynq_ultra_ps_e_0']['address_spaces']['Data']['segments']
new_addr=new['addressing']['/zynq_ultra_ps_e_0']['address_spaces']['Data']['segments']
for name,segment in old_addr.items():assert new_addr[name]==segment,name
checked=0
for kind,key in (('nets','ports'),('interface_nets','interface_ports')):
    candidates=[set(n[key]) for n in new[kind].values()]
    for name,net in old[kind].items():
        # Only the PDH coefficient port was renamed. Every old stream stays.
        ports=set(net[key])-{'pdh_tones_0/reference_coefficients'}
        if len(ports)>1:
            assert any(ports<=n for n in candidates),(name,ports)
            checked+=1


def linked(design,*ports):
    assert any(set(ports)<=set(n['ports']) for n in design['nets'].values()),ports


linked(new,'pdh_tones_0/gpio_clk','pdh_carrier_frequency/s_axi_aclk','pdh_modulation_frequency/s_axi_aclk')
linked(new,'pdh_amplitudes/gpio2_io_o','pdh_tones_0/reference_settings')
for oscillator in ('carrier','modulation'):
    for word,pin in (('low','gpio_io_o'),('high','gpio2_io_o')):
        linked(new,f'pdh_{oscillator}_frequency/{pin}',f'pdh_tones_0/{oscillator}_fcw_{word}')
for name,fcw in [('carrier',98170681051429),('modulation',4908534052571)]:
    params=new['components'][f'pdh_{name}_frequency']['parameters']
    low=int(params['C_DOUT_DEFAULT']['value'],16)
    high=int(params['C_DOUT_DEFAULT_2']['value'],16)
    assert low|(high<<32)==fcw,(name,low,high)
h=new['components']['photon_counting']
linked(h,'hist_counter_0/gpio_clk','axi_gpio_0/s_axi_aclk')
linked(h,'pmod_sync_edge_0/sync_edge','hist_counter_0/input_edge')
linked(h,'pmod_debounce_sync_2/event_pulse','hist_counter_0/trigger')
assert any(set(n['interface_ports'])=={'photon_counting/M_AXI','smartconnect_0/S09_AXI'} for n in new['interface_nets'].values())
assert any(set(n['interface_ports'])=={'M_AXI','axi_dma_3/M_AXI_S2MM'} for n in h['interface_nets'].values())
params=h['components']['axi_dma_3']['parameters']
assert params['c_include_mm2s']['value']=='0' and params['c_sg_length_width']['value']=='20'
# Generated RTL: clock and FCW connections must not be lost by module refresh.
rtl=(ROOT/'TransportPhaseLockFF.gen/sources_1/bd/design_1/synth/design_1.v').read_text()
pdh=re.search(r'\bpdh_tones_0\s*\((.*?)\);',rtl,re.S).group(1)
assert '.reference_settings(pdh_amplitudes_gpio2_io_o)' in pdh
for name in ('carrier','modulation'):
    assert f'.{name}_fcw_low(pdh_{name}_frequency_gpio_io_o)' in pdh
    assert f'.{name}_fcw_high(pdh_{name}_frequency_gpio2_io_o)' in pdh
result=dict(status='pass',preserved_signal_nets=checked,
            existing_converter_and_controller_parameters_unchanged=True,
            existing_peripheral_addresses_unchanged=True,photon_dma_ddr_connected=True)
(OUT/'connectivity_check.json').write_text(json.dumps(result,indent=2)+'\n')
print(f'PASS: {checked} existing nets preserved; FCW controls and photon DMA connected.')
