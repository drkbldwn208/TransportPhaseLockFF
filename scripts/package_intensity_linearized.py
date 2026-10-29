"""Package the routed IS03 overlay, matched helpers, calibration and verification.

Run with the Python3.10 PYNQ-metadata validation environment. The user's shell
monitor owns pynq_overlays/; this script never writes that directory.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET

from pynqmetadata.frontends import Metadata
from check_intensity_servo import verify
from package_intensity_calibration import resources

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'build/intensity_linearized'
OUT=ROOT/'build/intensity_linearized_R7'
RELEASE='R7-IS03-calibrated-intensity'

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def copy_file(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)

def check_preserved_configuration(current_hwh):
    old=ET.parse(WORK/'backup/design_1.hwh').getroot()
    new=ET.parse(current_hwh).getroot()
    def rfdc_parameters(root):
        module=root.find(".//MODULE[@INSTANCE='usp_rf_data_converter_0']")
        return {p.get('NAME'):p.get('VALUE') for p in module.findall('./PARAMETERS/PARAMETER')}
    assert rfdc_parameters(old)==rfdc_parameters(new), 'RFDC settings changed'
    fields=('INSTANCE','SLAVEBUSINTERFACE','ADDRESSBLOCK','BASEVALUE','HIGHVALUE','MASTERBUSINTERFACE')
    addresses=lambda root:{tuple(m.get(k) for k in fields) for m in root.findall('.//MEMRANGE')}
    assert addresses(old)<=addresses(new), 'An existing memory mapping changed'
    old_instances={m.get('INSTANCE') for m in old.findall('.//MODULE')}
    added={m.get('INSTANCE'):m.get('BASEVALUE') for m in new.findall('.//MEMRANGE')
           if m.get('INSTANCE') not in old_instances}
    result=dict(rfdc_unchanged=True,original_addresses_unchanged=True,added_addresses=added)
    (WORK/'address_check.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    freeze=json.loads((WORK/'rtl_freeze.json').read_text())
    for name,value in freeze['files'].items():
        assert digest(ROOT/name)==value, f'Source changed during build: {name}'
    assert re.search(r'^INTENSITY_LINEARIZED_BITSTREAM_COMPLETE ', (WORK/'build.stdout').read_text(), re.M)
    timing=(OUT/'reports/timing_summary.rpt').read_text().split('Design Timing Summary',1)[1]
    values=re.search(r'^\s*(-?\d+\.\d+\s+.*)$',timing,re.M).group(1).split()
    slack=[float(values[k]) for k in (0,4,8)]
    assert min(slack)>=0 and all(int(values[k])==0 for k in (2,6,10)), values
    assert 'VIOLATED' not in (OUT/'reports/bus_skew.rpt').read_text()
    assert not re.search(r'\|\s*Error\s*\|',(OUT/'reports/drc.rpt').read_text())
    assert re.search(r'nets with routing errors\.+\s*:\s*0\s*:',(OUT/'reports/route_status.rpt').read_text())
    assert digest(OUT/'TransportPhaseLockFF.bit')==digest(ROOT/'TransportPhaseLockFF.runs/impl_1/design_1_wrapper.bit')
    hardware=Metadata(input=OUT/'TransportPhaseLockFF.hwh')
    (WORK/'hwh_metadata.log').write_text(f'PASS: actual PYNQ Metadata parser loaded {len(hardware.blocks)} blocks from this release HWH.\n')
    connections=verify()
    addresses=check_preserved_configuration(OUT/'TransportPhaseLockFF.hwh')
    for name in ['calibration_python','helper_tests','shot_python','shot_analysis_rms','shot_host_rms',
                 'notebook','connectivity','hwh_metadata']:
        log=WORK/(name+'.log'); text=log.read_text()
        assert ('PASS' in text or '\nOK\n' in text) and not any(x in text for x in ('Traceback','FAILED','Fatal:')),name
        copy_file(log,OUT/'tests'/log.name)
    for path in (WORK/'regressions').glob('*.log'):
        text=path.read_text()
        assert ('PASS' in text or '\nOK\n' in text) and not any(x in text for x in ('Traceback','FAILED','Fatal:')),path.name
        copy_file(path,OUT/'tests'/path.name)
    for name in ('compensator_test/result.json','core_test/xsim.log','sim_shots/xsim.log'):
        path=WORK/name
        if path.suffix == '.log':
            assert re.search(r'^PASS(?::|\s)',path.read_text(),re.M) and 'Fatal:' not in path.read_text(),name
        copy_file(path,OUT/'tests'/name.replace('/','_'))
    for path in (WORK/'lifted_model_review').glob('*'):
        if path.is_file():copy_file(path,OUT/'tests/lifted_model_review'/path.name)
    software=[
        'intensity_servo.py','intensity_servo.ipynb','intensity_shots.py','intensity_shot_analysis.py',
        'repair_intensity_hwh.py',
        'tp_intensity_rfsoc_buffer.py','tp_intensity_zmq_server.py','tp_intensity_host_schedule.py',
        'intensity_calibration.py','intensity_calibration.ipynb',
        'intensity_phase_calibration.py','intensity_phase_calibration.ipynb',
        'laser_pll.py','laser_pll_loop_sweep.py','laser_pll_phase_fra.py',
        'laser_pll_bringup.ipynb','laser_pll_loop_sweep.ipynb','laser_pll_phase_fra.ipynb']
    if RELEASE.endswith('PLL640'):
        software.append('laser_pll_3500MHz.ipynb')
    for name in software: copy_file(ROOT/'python_scripts'/name,OUT/name)
    copy_file(ROOT/'python_scripts/laser_pll.py',OUT/'laser_pll_R7.py')
    for name in ['intensity_linearized.md','intensity_shot_records.md','intensity_calibration.md',
                 'intensity_filtered_R7.md','intensity_power_upload.md','pll_3500_wide_phase.md']:
        copy_file(ROOT/'docs'/name,OUT/'docs'/name)
    description=(ROOT/'docs/intensity_linearized.md').read_text()
    readme=description.replace('../exports/intensity_servo_20261028/', 'intensity_servo_20261028/').replace('`python_scripts/intensity_servo.ipynb`', '`intensity_servo.ipynb`')
    readme=readme.replace('(intensity_power_upload.md)', '(docs/intensity_power_upload.md)')
    if RELEASE.endswith('PLL640'):
        readme='# R7 IS03 + wide-range second PLL\n\nSecond PLL stage 3: ±320 turns; primary unchanged. See `laser_pll_3500MHz.ipynb` and `docs/pll_3500_wide_phase.md`. Intensity low/high modes use 50/200 mW full scale; see `docs/intensity_power_upload.md`. Current routed timing is in `verification.json`; older IS03 figures below are identified as historical.\n\n'+readme
    (OUT/'README.md').write_text(readme)
    (OUT/'docs/intensity_linearized.md').write_text(description.replace('../exports/intensity_servo_20261028/', '../intensity_servo_20261028/'))
    analysis=ROOT/'exports/intensity_servo_20261028'
    for path in analysis.iterdir():
        if path.is_file(): copy_file(path,OUT/analysis.name/path.name)
    for path in (ROOT/'ILAData/10-28').glob('*.csv'):
        copy_file(path,OUT/analysis.name/'raw_data'/path.name)
    for name in freeze['files']:
        copy_file(ROOT/name,OUT/'source'/name)
    for path in [ROOT/'scripts/check_intensity_servo.py',Path(__file__).resolve()]:
        copy_file(path,OUT/'source/scripts'/path.name)
    for path in (ROOT/'tests').glob('*intensity*'):
        if path.is_file():copy_file(path,OUT/'source/tests'/path.name)
    for name in ['rtl_freeze.json','address_check.json','hwh_repair.json','sensor_ram_registers.json']:
        if (WORK/name).exists():copy_file(WORK/name,OUT/'tests'/name)
    utilization=(OUT/'reports/utilization.rpt').read_text()
    used=resources(utilization,'design_1_wrapper')
    core_used=resources(utilization,'intensity_linearized_0')
    capacity=dict(lut=425280,flip_flop=850560,bram_36_equivalent=1080,dsp=4272)
    result=dict(release=RELEASE,date=datetime.now(timezone.utc).isoformat(),
                fpga_pll_version='0xA7',intensity_fra_version='0x494E5402',
                calibrated_servo_version='0x49530301',shot_logger_version='0x49533031',
                hardware_programmed=False,setup_slack_ns=slack[0],hold_slack_ns=slack[1],pulse_slack_ns=slack[2],
                resources=used,percent_of_device={k:100*v/capacity[k] for k,v in used.items()},
                calibrated_controller_resources=core_used,
                calibrated_controller_percent_of_device={k:100*v/capacity[k] for k,v in core_used.items()},
                hwh_parsed_blocks=len(hardware.blocks),rf_settings_and_original_addresses_unchanged=addresses,
                feedback_latency_budget_s=11/245.76e6,leadlag_extra_latency_s=2/245.76e6,
                measured_plant_delay_s=1.0871322058444349e-6,proposed_crossover_hz=300000,
                higher_order_crossover_hz=150000,
                optimizer_cost='RMS calibrated measured optical tracking error in mW; faults are rejection criteria',
                notebook_feedforward_default=False,
                requested_above_500k_verified=False,
                limitations=['No physical optical-loop test or FPGA programming performed.',
                'Measured plant delay and available compensation do not establish stable >500kHz bandwidth.',
                'The requested 300kHz PI preset has only about 0.2dB modeled gain margin; lower-bandwidth PII/PIII presets target150kHz.',
                'FRA used large modulation; confirm small-signal response at reduced amplitude.',
                'Modeled feedforward improves smooth ramps but increases abrupt-step overshoot; compare on the actual shot.',
                'Sensor dark points absent; AOM model is approximate and incident power is an effective scale.',
                'Shot recording uses point decimation and assumes the existing continuous DAC path.',
                'Existing clock/external I/O constraint warnings remain.'])
    if RELEASE.endswith('PLL640'):
        root=ET.parse(OUT/'TransportPhaseLockFF.hwh').getroot()
        shifts=[]
        for name in ('laser_pll_0','laser_pll_1'):
            module=root.find(f".//MODULE[@INSTANCE='{name}']")
            value=module.find("./PARAMETERS/PARAMETER[@NAME='STAGE3_RANGE_SHIFT']").get('VALUE')
            shifts.append(int(value))
        assert shifts==[0,2], shifts
        result.update(pll_stage3_full_span_turns=[160,640],pll_added_latency_s=0,
                      intensity_full_scale_by_mode_mW=dict(low_power=50.,high_power=200.),
                      intensity_mapping_added_resources=0,intensity_mapping_added_latency_s=0,
                      inherited_rtl_tests='Unchanged intensity RTL: compensator, core, sampler and prior regressions from preceding IS03 build.',
                      fresh_tests=['primary/secondary PLL end-to-end stages','wide phase/rails/tracking gain',
                                   'PLL handoffs/scaler','Python PLL controls','intensity helper/mode scaling',
                                   'physical-power upload','shot recording/analysis','notebook syntax'])
        for name in ('power_upload.log','control.log','stages.log','acquisition.log','sim_wide_phase/xsim.log'):
            path=WORK/name; log=path.read_text()
            assert ('PASS' in log or '\nOK\n' in log) and not any(x in log for x in ('Traceback','FAILED','Fatal:')),name
            copy_file(path,OUT/'tests'/name.replace('/','_'))
        for path in (ROOT/'tests').glob('*laser_pll*'):
            if path.is_file():copy_file(path,OUT/'source/tests'/path.name)
    (OUT/'tests/connectivity.json').write_text(json.dumps(connections,indent=2)+'\n')
    result['files']={str(p.relative_to(OUT)):digest(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='verification.json'}
    (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    # Zip only the Python/docs/calibration deliverables; .bit/.hwh stay in OUT.
    package=OUT.with_name(OUT.name+'_python.zip')
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file() and p.suffix in ('.py','.ipynb','.md','.json','.png','.csv') and 'source' not in p.relative_to(OUT).parts:
                z.write(p,p.relative_to(OUT))
    with zipfile.ZipFile(package) as z:assert z.testzip() is None
    print(json.dumps({k:result[k] for k in ('setup_slack_ns','hold_slack_ns','resources','hwh_parsed_blocks')},indent=2))
    print('PASS: full routed timing, source freeze, HWH parse, existing paths and matched IS03 software package')

if __name__=='__main__':main()
