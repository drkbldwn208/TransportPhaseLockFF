"""Verify and package R7 phase-FRA hardware/software without overwriting A8."""
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from check_intensity_servo import verify as verify_intensity_servo

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build'
WORK=BUILD/'R7_FRA'
OUT=BUILD/'laser_pll_R7_FRA'
REPORTS=BUILD/'full_project'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    intensity_servo = verify_intensity_servo()
    freeze=json.loads((WORK/'rtl_freeze.json').read_text())
    for name,digest in freeze['files'].items():
        assert sha256(ROOT/name)==digest, f'RTL changed after freeze: {name}'
    for name in ('design_1_laser_pll_0_0_synth_1','design_1_laser_pll_1_0_synth_1','synth_1','impl_1'):
        run=ROOT/'TransportPhaseLockFF.runs'/name
        assert (run/'.vivado.begin.rst').stat().st_mtime>freeze['timestamp'], f'Stale {name}'
        assert (run/'.vivado.end.rst').exists() and not (run/'.vivado.error.rst').exists(), name
    run=ROOT/'TransportPhaseLockFF.runs/impl_1'
    assert 'write_bitstream completed successfully' in (run/'runme.log').read_text()
    bit=run/'design_1_wrapper.bit'
    hwh=ROOT/'TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh'
    assert sha256(OUT/'laser_pll.bit')==sha256(bit)
    assert sha256(OUT/'laser_pll.hwh')==sha256(hwh)

    bd_path=ROOT/'TransportPhaseLockFF.srcs/sources_1/bd/design_1/design_1.bd'
    bd=json.loads(bd_path.read_text())['design']
    assert bd['components']['usp_rf_data_converter_0']['parameters']==json.loads((WORK/'rfdc_before.json').read_text())
    nets=[set(n['interface_ports']) for n in bd['interface_nets'].values()]
    for pair in [('AxisConstant14Samples_0/m_axis','usp_rf_data_converter_0/s10_axis'),
                 ('laser_pll_0/m_rf_axis','usp_rf_data_converter_0/s12_axis'),
                 ('laser_pll_0/m_axis','usp_rf_data_converter_0/s11_axis'),
                 ('laser_pll_1/m_axis','usp_rf_data_converter_0/s13_axis'),
                 ('usp_rf_data_converter_0/m03_axis','laser_pll_0/s_axis'),
                 ('usp_rf_data_converter_0/m11_axis','laser_pll_1/s_axis')]:
        assert any(set(pair)<=net for net in nets), pair
    hw=ET.parse(hwh).getroot()
    modules={m.get('INSTANCE') for m in hw.findall('.//MODULE')}
    addresses={m.get('INSTANCE'):m.get('BASEVALUE') for m in hw.findall('.//MEMRANGE') if m.get('MEMTYPE')=='REGISTER'}
    assert {'pll_rf_source','laser_pll_0','laser_pll_1','pll2_iq_dma'}<=modules
    assert not {'pll_loopback_i','pll_loopback_q'} & modules
    assert int(addresses['pll_rf_source'],16)==0xA0300000
    for prefix in ('pll','pll2'):
        for suffix in ('iir','iir_feed','iir_pole','fra_counts','fra_extrema','fra_samples'):
            assert prefix+'_'+suffix in addresses

    report_names=('timing_summary.rpt','utilization.rpt','drc.rpt','clock_interaction.rpt',
                  'pll_setup_paths.rpt','pll_hold_paths.rpt')
    for name in report_names:
        assert (REPORTS/name).stat().st_mtime>freeze['timestamp'],f'Stale report {name}'
    assert bit.stat().st_mtime>(REPORTS/'timing_summary.rpt').stat().st_mtime
    table=(REPORTS/'timing_summary.rpt').read_text().split('Design Timing Summary',1)[1]
    values=re.search(r'^\s*(-?\d+\.\d+\s+.*)$',table,re.M).group(1).split()
    setup_ns,hold_ns,pulse_ns=(float(values[k]) for k in (0,4,8))
    assert min(setup_ns,hold_ns,pulse_ns)>=0
    assert all(int(values[k])==0 for k in (2,6,10))
    assert not re.search(r'\|\s*Error\s*\|',(REPORTS/'drc.rpt').read_text())
    # Export reports the final bitstream design, after post-route optimization.
    skew=REPORTS/'bus_skew.rpt'
    route=REPORTS/'route_status.rpt'
    assert skew.stat().st_mtime>freeze['timestamp'] and 'VIOLATED' not in skew.read_text()
    assert route.stat().st_mtime>freeze['timestamp']
    assert re.search(r'nets with routing errors\.+\s*:\s*0\s*:',route.read_text())
    intensity_route=REPORTS/'intensity_servo_routed.rpt'
    assert intensity_route.stat().st_mtime>freeze['timestamp']
    assert 'PASS: all 64 intensity ADC input bits driven by RFDC' in intensity_route.read_text()
    intensity_bits=re.findall(r'adc_bus\[(\d+)\] <- .*rx0_u_adc/DATA_ADC1\[(\d+)\]',intensity_route.read_text())
    assert len(intensity_bits)==64 and len({b for b,_ in intensity_bits})==64
    # Four 16-bit I words from the interleaved I/Q ADC bus; Q stays on the monitor path.
    assert all(int(source)==32*(int(sink)//16)+int(sink)%16 for sink,source in intensity_bits)
    top=next(line for line in (REPORTS/'utilization.rpt').read_text().splitlines()
             if re.match(r'\|\s*design_1_wrapper\s*\|',line))
    counts=[int(x.strip()) for x in top.split('|')[3:-1]]
    resources=dict(lut=counts[0],flip_flop=counts[4],bram_36_equivalent=counts[5]+counts[6]/2,dsp=counts[8])

    tests={
        'control_python':('tests/test_laser_pll_control.py','Ran 23 tests'),
        'legacy_fra_python':('tests/test_laser_pll_loop_sweep.py','Ran 18 tests'),
        'phase_fra_python':('tests/test_laser_pll_phase_fra.py','Ran 6 tests'),
        'pll_rtl':('tests/test_laser_pll.py','ADC word -> DAC register latency: 18 clocks'),
        'stages_rtl':('tests/test_laser_pll_stages.py','PASS'),
        'fra_hls_rtl':('tests/test_laser_pll_fra.py','7-clock RF delay recovered'),
        'rf_pm_rtl':('tests/test_laser_pll_rf_pm.py','PASS: RF PM quadrants'),
        'phase_notebook':('tests/test_laser_pll_phase_fra_notebook.py','PASS: complete R7 phase FRA notebook'),
        'bringup_notebook':('tests/test_laser_pll_notebook.py','PASS: 19 notebook code cells'),
        'legacy_notebook':('tests/test_laser_pll_loop_notebook.py','PASS: all'),
        'dual_bd':('tests/test_laser_pll_dual_bd.py','PASS: independent dual PLL'),
        'intensity_servo':('tests/test_intensity_servo.py','PASS: regenerated intensity path connected'),
    }
    for directory in ('reports','docs','tests'): (OUT/directory).mkdir(exist_ok=True)
    results={}
    for name,(script,marker) in tests.items():
        log=WORK/(name+'.log');body=log.read_text()
        assert marker in body and 'Traceback' not in body and 'FAILED' not in body, name
        if 'python' in name:assert '\nOK\n' in body,name
        results[name]=dict(status='pass',script=script,script_sha256=sha256(ROOT/script),
                           log_sha256=sha256(log),completed=datetime.fromtimestamp(log.stat().st_mtime).isoformat())
        shutil.copy2(log,OUT/'tests'/log.name)
    (OUT/'tests/results.json').write_text(json.dumps(results,indent=2)+'\n')
    (OUT/'tests/intensity_servo_connections.json').write_text(json.dumps(intensity_servo,indent=2)+'\n')
    for name in ('laser_pll.py','laser_pll_loop_sweep.py','laser_pll_phase_fra.py',
                 'laser_pll_bringup.ipynb','laser_pll_loop_sweep.ipynb','laser_pll_phase_fra.ipynb'):
        shutil.copy2(ROOT/'python_scripts'/name,OUT/name)
    assert 'FPGA_VERSION = 0xA7' in (OUT/'laser_pll.py').read_text()
    assert 'FEATURE_VERSION = 0x52463701' in (OUT/'laser_pll_phase_fra.py').read_text()
    shutil.copy2(OUT/'laser_pll.py',OUT/'laser_pll_R7.py')
    for name in report_names:shutil.copy2(REPORTS/name,OUT/'reports'/name)
    shutil.copy2(skew,OUT/'reports/bus_skew.rpt');shutil.copy2(route,OUT/'reports/route_status.rpt')
    shutil.copy2(intensity_route,OUT/'reports/intensity_servo_routed.rpt')
    for name in ('laser_pll_rf_fra_R7.md','laser_pll_A7.md','laser_pll_loopback_A8.md','laser_pll_rtl_walkthrough.md','laser_pll.md','overlay_versions.md'):
        shutil.copy2(ROOT/'docs'/name,OUT/'docs'/name)
    for name in freeze['files']:
        target=OUT/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    (OUT/'README.md').write_text(f'''# R7 RF-FRA with restored intensity servo — {datetime.now():%Y-%m-%d}

Matched hardware and helpers: PLL signature 0xA7, feature GPIO 0x52463701.
This is R7 plus phase-FRA, not the original R7 image or A8 loopback image.

- Normal dual PLL/acquisition/tracking/IIR/IQ-DMA behavior restored from R7.
- Intensity ADC224/1 data/valid reconnected to iq_split_0 and fast PI; actual
  generated HWH/RTL connectivity checked. LO and 32-bit command path preserved.
- Closed optical loop: error-output injection on DAC229/1, raw phase at ADC224/3;
  measures Phi/D and full return ratio L=(D-U)/U, including the discriminator.
- RF chain: phase-modulated DAC229/2 carrier → amplifiers → ADC224/3;
  measures received/applied phase in rad/rad. Default carrier 800.01 MHz.
- Legacy E/U FRA remains available. One primary analyzer mode at a time.
- No feedback clocks added. RFDC configuration and ADC225/0,2 paths retained.
- At least 1 s integration and 8 complex repeats by default; CSV/block CSV/JSON/PNG.
- New notebook: laser_pll_phase_fra.ipynb. Default startup only refreshes helpers;
  set initialize_hardware=True to download. Reprogramming interrupts locks.
- Copy BOTH bit/HWH to the board, keeping matching basenames. Notebook uses
  /home/xilinx/Bitfiles/FreqLocksBranch/overlays/TransportPhaseLockFF.bit.
- Copy all three helpers plus laser_pll_R7.py together; the versioned file is an
  exact copy of laser_pll.py. Follow the notebook's explicit reload/binding cell.
- A8 diagnostic package is preserved separately; its helpers need its A8 image.

Routed setup/hold/pulse-width slack: {setup_ns:+.3f}/{hold_ns:+.3f}/{pulse_ns:+.3f} ns.
No failing timing endpoints, routing errors or bitstream DRC errors. Existing
clock/external-I/O constraint limitations remain. Hardware has not been programmed.
See docs/laser_pll_rf_fra_R7.md and verification.json for boundaries and evidence.
''')
    manifest=dict(date=datetime.now().isoformat(timespec='seconds'),release_revision='R7-FRA-intensity-repair',
                  fpga_version='0xA7',feature_version='0x52463701',
                  vivado='2024.1',part='xczu49dr-ffvf1760-2-e',programmed_hardware=False,
                  full_board_synthesis_route_bitstream_complete=True,setup_slack_ns=setup_ns,
                  hold_slack_ns=hold_ns,pulse_width_slack_ns=pulse_ns,
                  setup_failing_endpoints=0,hold_failing_endpoints=0,pulse_width_failing_endpoints=0,
                  bus_skew_violations=0,routing_errors=0,bitstream_drc_errors=0,resources=resources,
                  fabric_clock_hz=245760000,fra_added_feedback_clocks=0,
                  adc_to_dac_register_clocks_bypass={'stage_0':18,'stage_2':18,'stage_3':20,'stage_4':23},
                  iir_added_clocks=[2,3],rf_pm_source_clocks=4,phase_probe_clocks=1,
                  adc_rail_diagnostic_clocks=1,
                  phase_codes_per_turn=262144,phase_observer_range_turns=[-2,2],
                  rf_pm_phase_grid_codes_per_turn=65536,feedback_winding_bits=24,
                  rf_converter_parameters_unchanged=True,old_adc225_0_2_paths_preserved=True,
                  intensity_servo_restored=intensity_servo,
                  closed_fra=dict(dac='229/1',adc='224/3',response_units='rad/DAC-code',return_ratio='(D-U)/U'),
                  rf_fra=dict(dac='229/2',adc='224/3',response_units='rad/rad',default_carrier_hz=800.01e6),
                  limitations=['No optical-loop or physical converter bench validation of this release.',
                               'Existing clock/external-I/O constraint limitations remain.',
                               'Phase observer clips outside +/-2 turns relative to arm; feedback slip memory is separate.',
                               'Noise/clipping/drift can bias FRA; inspect blocks and repeat amplitudes.'],
                  rtl_freeze=freeze,bd_sha256=sha256(bd_path),test_results=results,
                  register_addresses={k:v for k,v in addresses.items() if k.startswith('pll')})
    manifest['files']={str(p.relative_to(OUT)):sha256(p) for p in sorted(OUT.rglob('*'))
                       if p.is_file() and p.name!='verification.json'}
    (OUT/'verification.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name,software_only in [('laser_pll_R7_FRA.zip',False),('laser_pll_R7_FRA_python.zip',True)]:
        with zipfile.ZipFile(BUILD/name,'w',zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(OUT.rglob('*')):
                if p.is_file() and (not software_only or p.suffix in ('.py','.ipynb','.md','.json')):
                    archive.write(p,str(p.relative_to(OUT)))
        with zipfile.ZipFile(BUILD/name) as archive:assert archive.testzip() is None
    latest=ROOT/'pynq_overlays/latest';latest.mkdir(parents=True,exist_ok=True)
    shutil.copy2(OUT/'laser_pll.bit',latest/'TransportPhaseLockFF.bit')
    shutil.copy2(OUT/'laser_pll.hwh',latest/'TransportPhaseLockFF.hwh')
    print(json.dumps({k:manifest[k] for k in ('fpga_version','feature_version','setup_slack_ns','hold_slack_ns','resources')},indent=2))
    print('R7 RF-FRA package:',BUILD/'laser_pll_R7_FRA.zip')


if __name__=='__main__':main()
