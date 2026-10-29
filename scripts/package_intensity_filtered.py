"""Package only the timing-verified INT2 build; preserve previous archives."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from check_intensity_servo import verify
from package_intensity_calibration import resources
from pynqmetadata.frontends import Metadata
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python_scripts'))
from repair_int2_hwh import ORIGINAL_SHA256, corrected_hwh
WORK=ROOT/'build/intensity_filtered'
OUT=ROOT/'build/intensity_filtered_R7'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    freeze=json.loads((WORK/'rtl_freeze.json').read_text())
    for name,h in freeze['files'].items():assert digest(ROOT/name)==h,name
    assert 'INTENSITY_FILTERED_BITSTREAM_COMPLETE' in (WORK/'build_final.stdout').read_text()
    report=(OUT/'reports/timing_summary.rpt').read_text().split('Design Timing Summary',1)[1]
    values=re.search(r'^\s*(-?\d+\.\d+\s+.*)$',report,re.M).group(1).split()
    slack=[float(values[k]) for k in (0,4,8)]
    assert min(slack)>=0 and all(int(values[k])==0 for k in (2,6,10))
    assert 'VIOLATED' not in (OUT/'reports/bus_skew.rpt').read_text()
    assert not re.search(r'\|\s*Error\s*\|',(OUT/'reports/drc.rpt').read_text())
    assert re.search(r'nets with routing errors\.+\s*:\s*0\s*:',(OUT/'reports/route_status.rpt').read_text())
    assert 'PASS: ADC224/1 I/Q drives filter' in (OUT/'reports/intensity_servo_routed.rpt').read_text()
    cic=(OUT/'reports/intensity_cic_dsp.rpt').read_text()
    below=re.findall(r'^Below: (DSP48E2_X\d+Y\d+) cells=(.*)$',cic,re.M)
    assert len(below)==2 and all(not cells.strip() for site,cells in below)
    gen=ROOT/'TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh'
    # The released INT2 bitstream ties unused ILA slots to zero. Repair only
    # that known HWH's sink-only metadata, retaining the raw export as evidence.
    raw_hwh=gen.read_bytes()
    metadata_repaired=digest(gen)==ORIGINAL_SHA256
    expected_hwh=corrected_hwh(raw_hwh) if metadata_repaired else raw_hwh
    release_hwh=OUT/'TransportPhaseLockFF.hwh'
    assert release_hwh.read_bytes() in (raw_hwh,expected_hwh)
    raw_copy=OUT/'source/metadata/design_1_original.hwh'
    raw_copy.parent.mkdir(parents=True,exist_ok=True)
    raw_copy.write_bytes(raw_hwh)
    if release_hwh.read_bytes()!=expected_hwh:release_hwh.write_bytes(expected_hwh)
    metadata=Metadata(input=release_hwh)
    assert digest(ROOT/'TransportPhaseLockFF.runs/impl_1/design_1_wrapper.bit')==digest(OUT/'TransportPhaseLockFF.bit')
    connections=verify()
    bd=json.loads((ROOT/'TransportPhaseLockFF.srcs/sources_1/bd/design_1/design_1.bd').read_text())['design']
    old=json.loads((WORK/'backup/design_1.bd').read_text())['design']
    changes={}
    for name,previous in old['components'].items():
        a=previous.get('parameters',{});b=bd['components'][name].get('parameters',{})
        diff={k:[a.get(k),b.get(k)] for k in set(a)|set(b) if a.get(k)!=b.get(k)}
        if diff:changes[name]=diff
    assert set(changes)<= {'usp_rf_data_converter_0','cic_compiler_2'},changes
    assert set(changes['usp_rf_data_converter_0'])=={'ADC_Nyquist11'}
    assert bd['components']['usp_rf_data_converter_0']['parameters']['ADC_Nyquist11']['value']=='1'
    def addresses(path):
        return {m.get('INSTANCE'):m.get('BASEVALUE') for m in ET.parse(path).findall('.//MEMRANGE') if m.get('MEMTYPE')=='REGISTER'}
    assert addresses(WORK/'backup/TransportPhaseLockFF.hwh')==addresses(gen),'Address map changed'
    hw=ET.parse(gen).getroot();mods={m.get('INSTANCE'):m for m in hw.findall('.//MODULE')}
    for name in ['cic_compiler_2','intensity_cal_q']:
        p={x.get('NAME'):x.get('VALUE') for x in mods[name].findall('./PARAMETERS/PARAMETER')}
        assert p['Quantization']=='Full_Precision' and int(p['C_OUTPUT_WIDTH'])==55,p
    logs=['filter_test','phase_monitor','phase_helper','pll_control','pll_acquisition','pll_tones',
          'intensity_probe','intensity_fifo','intensity_python','notebook','connectivity','dual_bd','pll_iir','pll_fra']
    if metadata_repaired:logs.append('hwh_metadata')
    for name in logs:
        text=(WORK/(name+'.log')).read_text()
        assert ('PASS:' in text or '\nOK\n' in text) and not any(x in text for x in ['Traceback','FAILED','Fatal:']),name
    (OUT/'tests').mkdir(exist_ok=True);(OUT/'docs').mkdir(exist_ok=True)
    for name in logs:shutil.copy2(WORK/(name+'.log'),OUT/'tests')
    for name in ['repair_int2_hwh.py','intensity_calibration.py','intensity_calibration.ipynb','intensity_phase_calibration.py',
                 'intensity_phase_calibration.ipynb','laser_pll.py','laser_pll_loop_sweep.py','laser_pll_phase_fra.py',
                 'laser_pll_bringup.ipynb','laser_pll_loop_sweep.ipynb','laser_pll_phase_fra.ipynb']:
        shutil.copy2(ROOT/'python_scripts'/name,OUT/name)
    shutil.copy2(OUT/'laser_pll.py',OUT/'laser_pll_R7.py')
    for name in ['intensity_filtered_R7.md','intensity_calibration.md','laser_pll_A7.md','laser_pll_rf_fra_R7.md']:
        shutil.copy2(ROOT/'docs'/name,OUT/'docs')
    shutil.copy2(ROOT/'docs/intensity_filtered_R7.md',OUT/'README.md')
    shutil.copy2(WORK/'filter_response.png',OUT/'docs')
    shutil.copy2(WORK/'filter_test/result.json',OUT/'tests/filter_response.json')
    (OUT/'tests/connectivity.json').write_text(json.dumps(connections,indent=2)+'\n')
    for name in freeze['files']:
        target=OUT/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    # Preserve the as-built Tcl already archived with this bitstream. The scalar
    # ILA wiring correction is for a future build and has not changed the .bit.
    setup=ROOT/'scripts/add_intensity_lowpass.tcl'
    if metadata_repaired:
        target=OUT/'future_build'/setup.name;target.parent.mkdir(exist_ok=True);shutil.copy2(setup,target)
    else:shutil.copy2(setup,OUT/'source/scripts'/setup.name)
    for path in [ROOT/'scripts/build_intensity_filtered.tcl',
                 ROOT/'scripts/finish_intensity_filtered.tcl',ROOT/'scripts/check_intensity_servo_routed.tcl',Path(__file__).resolve()]:
        target=OUT/'source/scripts'/path.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    text=(OUT/'reports/utilization.rpt').read_text();used=resources(text,'design_1_wrapper');filt=resources(text,'intensity_rx_lowpass_0')
    capacity=dict(lut=425280,flip_flop=850560,bram_36_equivalent=1080,dsp=4272)
    result=dict(date=datetime.now(ZoneInfo('America/Los_Angeles')).isoformat(),release='R7-INT2-filtered-3g5',
        fpga_version='0xA7',intensity_feature_version='0x494E5402',hardware_programmed=False,
        setup_slack_ns=slack[0],hold_slack_ns=slack[1],pulse_slack_ns=slack[2],
        resources=used,filter_resources=filt,filter_percent_of_device={k:100*v/capacity[k] for k,v in filt.items()},
        receiver=json.loads((WORK/'filter_test/result.json').read_text()),
        second_pll=dict(reference_hz=3.5e9,signed_alias_hz=-432.16e6,adc='225/1',dac='229/3',nyquist_driver_value=2),
        configuration_changes=changes,register_map_unchanged=True,rtl_freeze=freeze,
        cic_unused_below_sites=[site for site,cells in below],
        hwh_metadata=dict(repaired=metadata_repaired,raw_sha256=digest(gen),release_sha256=digest(release_hwh),
                          parsed_blocks=len(metadata.blocks),parser='pynqmetadata 0.1.5 / Python 3.10'),
        tests=logs,limitations=['No physical optical lock or hardware programming performed.','Existing clock/external I/O constraint warnings remain.','DMA point decimation can alias signals other than the suppressed mixer image.']+
            (['ILA slots 0/1/5 are tied to zero in this bitstream; use slot 4 during a phase DMA capture.'] if metadata_repaired else []))
    result['files']={str(p.relative_to(OUT)):digest(p) for p in OUT.rglob('*') if p.is_file() and p.name!='verification.json'}
    (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    for software in (False,True):
        path=ROOT/'build'/('intensity_filtered_R7_python.zip' if software else 'intensity_filtered_R7.zip')
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(OUT.rglob('*')):
                if p.is_file() and (not software or p.suffix in ['.py','.ipynb','.md','.json','.png']):z.write(p,p.relative_to(OUT))
        with zipfile.ZipFile(path) as z:assert z.testzip() is None
    # The user's shell monitor owns pynq_overlays/latest and dated overlay copies.
    print(json.dumps({k:result[k] for k in ['setup_slack_ns','hold_slack_ns','resources','filter_resources']},indent=2))
    print('PASS: timing, source hashes, both PLLs, unchanged register map, raw ADC clipping and filtered PI connectivity; packaged INT2')
if __name__=='__main__':main()
