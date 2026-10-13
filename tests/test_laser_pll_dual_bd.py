"""Check saved converter/AXI wiring independently of Vivado's width checks."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=json.loads((ROOT/'TransportPhaseLockFF.srcs/sources_1/bd/design_1/design_1.bd').read_text())['design']
c=p['components']; r=c['usp_rf_data_converter_0']['parameters']
for tile in (0,1): assert float(r[f'ADC{tile}_Sampling_Rate']['value'])==1.96608
assert float(r['DAC1_Sampling_Rate']['value'])==6.88128
for key in ('ADC_Slice10_Enable','ADC_Slice11_Enable','ADC_Slice12_Enable','DAC_Slice13_Enable'):
    assert r[key]['value']=='true', key
nets=[set(n['interface_ports']) for n in p['interface_nets'].values()]
def linked(*ports):
    assert any(set(ports)<=net for net in nets),ports
linked('usp_rf_data_converter_0/m03_axis','laser_pll_0/s_axis')
linked('usp_rf_data_converter_0/m11_axis','laser_pll_1/s_axis')
linked('laser_pll_0/m_axis','usp_rf_data_converter_0/s11_axis')
linked('laser_pll_1/m_axis','usp_rf_data_converter_0/s13_axis')
linked('usp_rf_data_converter_0/m10_axis','axis_broadcaster_2/S_AXIS')
linked('usp_rf_data_converter_0/m12_axis','axis_broadcaster_3/S_AXIS')
linked('laser_pll_1/m_monitor','pll2_iq_fifo/S_AXIS')
linked('pll2_iq_fifo/M_AXIS','pll2_iq_dma/S_AXIS_S2MM')
linked('pll2_iq_dma/M_AXI_S2MM','smartconnect_0/S08_AXI')
for i,prefix in enumerate(('pll','pll2')):
    block=f'laser_pll_{i}'
    linked(prefix+'_fra_tone/perturb_err_out',block+'/s_fra_tone')
    for name in ('error','drive'):
        linked(block+'/m_fra_'+name,prefix+'_fra_'+name+'/probe_in')
        linked(block+'/m_fra_'+name+'_ref',prefix+'_fra_'+name+'/ref_in')
    scalar_nets=[set(n['ports']) for n in p['nets'].values()]
    for suffix,pin in (('iir','iir_control'),('iir_feed','iir_b0'),('iir_pole','iir_pole')):
        assert any({prefix+'_'+suffix+'/gpio_io_o',block+'/'+pin}<=n for n in scalar_nets)
print('PASS: independent dual PLL/FRA/DMA/IIR wiring; old ADC225/0,2 paths/rates retained')
