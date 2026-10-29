"""Check physical signal connectivity, not just the drawn AXIS interfaces.

Checks the generated HWH and Verilog for the intended physical signal paths.
No hardware is programmed. Run after BD generation and before packaging.
"""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / 'TransportPhaseLockFF.gen/sources_1/bd/design_1'


def check_connections(hwh):
    modules = {m.get('INSTANCE'): m for m in hwh.findall('.//MODULE')}
    ports = {name: {p.get('NAME').lower(): p.attrib for p in m.findall('./PORTS/PORT')}
             for name, m in modules.items()}
    connections = []

    def linked(source, sink):
        a, b = (ports[module][pin.lower()] for module, pin in (source, sink))
        assert a['DIR'] == 'O' and b['DIR'] == 'I', (source, sink)
        assert a.get('SIGNAME') and a['SIGNAME'] == b.get('SIGNAME'), (source, sink, a, b)
        # Vivado represents a scalar and a [0:0] vector differently in HWH.
        width = lambda p: abs(int(p.get('LEFT', 0)) - int(p.get('RIGHT', 0))) + 1
        assert width(a) == width(b), (source, sink)
        connections.append({'source': '/'.join(source), 'sink': '/'.join(sink), 'net': a['SIGNAME']})

    def stream(source, source_bus, sink, sink_bus):
        for signal in ('tdata', 'tvalid'):
            linked((source, source_bus + '_' + signal), (sink, sink_bus + '_' + signal))

    stream('usp_rf_data_converter_0', 'm01_axis', 'iq_split_0', 's_axis')
    filtered = 'intensity_rx_lowpass_0' in modules
    sensor = ('intensity_rx_lowpass_0', 'filtered_i') if filtered else ('iq_split_0', 'adc_bus')
    sensor_valid = ('intensity_rx_lowpass_0', 'filtered_valid') if filtered else ('iq_split_0', 'm_axis_i_tvalid')
    linked(sensor, ('fast_servo_controller_0', 'adc_bus'))
    if filtered:
        linked(('iq_split_0', 'm_axis_i_tdata'), ('intensity_rx_lowpass_0', 'i_data'))
        linked(('iq_split_0', 'm_axis_q_tdata'), ('intensity_rx_lowpass_0', 'q_data'))
        linked(sensor, ('cordic_average_0', 's_axis_i_tdata'))
        linked(('intensity_rx_lowpass_0', 'filtered_q'), ('cordic_average_0', 's_axis_q_tdata'))
        linked(('iq_split_0', 'adc_bus'), ('intensity_probe_0', 'adc_rail_bus'))
        for axis, cic in [('i','cic_compiler_2'),('q','intensity_cal_q')]:
            linked(('intensity_cal_'+axis+'_slice', 'Dout'), (cic, 's_axis_data_tdata'))
            linked((cic, 'm_axis_data_tdata'), ('intensity_cal_'+axis+'_scale', 'Din'))
            linked(('intensity_cal_'+axis+'_scale', 'Dout'), ('intensity_cal_iq', 'In0' if axis=='i' else 'In1'))
            params={p.get('NAME'):p.get('VALUE') for p in modules[cic].findall('./PARAMETERS/PARAMETER')}
            assert params['Quantization']=='Full_Precision' and int(params['C_OUTPUT_WIDTH'])==55
            assert int(params['C_RATE'])==8192 and int(params['C_NUM_STAGES'])==3
        linked(('intensity_cal_iq', 'dout'), ('cordic_0', 's_axis_cartesian_tdata'))
        linked(('cordic_0', 'm_axis_dout_tdata'), ('axis_tlast_gen_3', 's_axis_tdata'))
    stream('axi_dma_6', 'm_axis_mm2s', 'dwell_fcw_streamer_32_0', 's_axis_cmd')
    linked(('dwell_fcw_streamer_32_0', 's_axis_cmd_tready'), ('axi_dma_6', 'm_axis_mm2s_tready'))
    linked(('dwell_fcw_streamer_32_0', 'fcw_out'), ('setpoint_switch_0', 'serial_setpoint'))
    linked(('setpoint_switch_0', 'setpoint_out'), ('fast_servo_controller_0', 'set_point'))
    if 'intensity_probe_0' in modules:
        if 'intensity_linearized_0' in modules:
            linked(('fast_servo_controller_0', 'dac_out'), ('intensity_linearized_0', 'legacy_command'))
            linked(('intensity_linearized_0', 'command_out'), ('intensity_probe_0', 'controller_command'))
            linked(sensor, ('intensity_linearized_0', 'adc_bus'))
            linked(sensor_valid, ('intensity_linearized_0', 'adc_valid'))
            linked(('setpoint_switch_0', 'setpoint_out'), ('intensity_linearized_0', 'reference_in'))
            linked(('dwell_fcw_streamer_32_0', 'active_r'), ('intensity_shot_capture_0', 'shot_active'))
            for signal in ('error_q8', 'reference_power', 'measured_power', 'raw_adc', 'sample_flags'):
                linked(('intensity_linearized_0', signal), ('intensity_shot_capture_0', signal))
            linked(('intensity_probe_0', 'command_out'), ('intensity_shot_capture_0', 'actuator_codes'))
            stream('intensity_shot_capture_0', 'm_axis', 'intensity_shot_fifo', 's_axis')
            stream('intensity_shot_fifo', 'm_axis', 'intensity_shot_dma', 's_axis_s2mm')
        else:
            linked(('fast_servo_controller_0', 'dac_out'), ('intensity_probe_0', 'controller_command'))
        linked(('intensity_probe_0', 'command_out'), ('sync_axis_power_mod_0', 'sync_in'))
        linked(sensor, ('intensity_probe_0', 'adc_bus'))
        linked(sensor_valid, ('intensity_probe_0', 'adc_valid'))
        linked(('pll_fra_one', 'dout'), ('intensity_probe_0', 'dac_ready'))
        ready = {p.get('NAME'): p.get('VALUE') for p in modules['pll_fra_one'].findall('./PARAMETERS/PARAMETER')}
        assert int(ready['CONST_VAL'], 0) == 1 and int(ready['CONST_WIDTH']) == 1
        stream('intensity_probe_0', 'm_axis', 'intensity_fifo', 's_axis')
        stream('intensity_fifo', 'm_axis', 'intensity_dma', 's_axis_s2mm')
        params={p.get('NAME'):p.get('VALUE') for p in modules['xlconstant_2'].findall('./PARAMETERS/PARAMETER')}
        assert int(params['CONST_VAL'], 0) == 0
        assert ports['sync_axis_power_mod_0']['open_loop_toggle']['SIGNAME'] == ports['xlconstant_2']['dout']['SIGNAME']
    else:
        linked(('fast_servo_controller_0', 'dac_out'), ('sync_axis_power_mod_0', 'sync_in'))
    stream('sync_axis_power_mod_0', 'm_axis', 'usp_rf_data_converter_0', 's03_axis')
    linked(('axi_gpio_12', 'gpio_io_o'), ('axis_power_mod_0', 'async_in'))
    stream('axis_power_mod_0', 'm_axis', 'cordic_1', 's_axis_cartesian')
    linked(('axi_gpio_10', 'gpio_io_o'), ('cordic_phase_helper_0', 'gpio_phase_in'))
    stream('cordic_phase_helper_0', 'm_axis_phase', 'cordic_1', 's_axis_phase')
    stream('cordic_1', 'm_axis_dout', 'PostCordicExtension_0', 's_axis')
    stream('PostCordicExtension_0', 'm_axis', 'usp_rf_data_converter_0', 's01_axis')
    assert ports['dwell_fcw_streamer_32_0']['s_axis_cmd_tdata']['LEFT'] == '31'
    return connections


def verify():
    hwh_path = GENERATED / 'hw_handoff/design_1.hwh'
    rtl_path = GENERATED / 'synth/design_1.v'
    hwh = ET.parse(hwh_path).getroot()
    connections = check_connections(hwh)
    # The elaborated wrapper must connect the very same wire at both ends.
    rtl = rtl_path.read_text()
    for signal in ('tdata', 'tvalid'):
        receiver = re.search(r'\biq_split_0\s*\((.*?)\);', rtl, re.S).group(1)
        driver = re.search(r'\busp_rf_data_converter_0\s*\((.*?)\);', rtl, re.S).group(1)
        source = re.search(r'\.m01_axis_' + signal + r'\(([^)]+)\)', driver).group(1)
        sink = re.search(r'\.s_axis_' + signal + r'\(([^)]+)\)', receiver).group(1)
        assert source == sink and re.fullmatch(r'\w+', sink), (signal, source, sink)

    result = dict(status='pass', connections=connections,
                  hwh_sha256=hashlib.sha256(hwh_path.read_bytes()).hexdigest(),
                  generated_rtl_sha256=hashlib.sha256(rtl_path.read_bytes()).hexdigest())
    return result


if __name__ == '__main__':
    result = verify()
    output = ROOT / 'build/R7_FRA/intensity_servo_connections.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('PASS: intensity ADC/PI/DAC, LO and 32-bit command connectivity in generated HWH/RTL')
