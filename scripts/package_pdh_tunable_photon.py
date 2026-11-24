"""Package validated local outputs; never write pynq_overlays or program hardware."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/PDH_TUNABLE_PHOTON'
reports=OUT/'reports'
log=(OUT/'resume.log').read_text()
assert 'PDH_TUNABLE_PHOTON_BITSTREAM_COMPLETE' in log
assert 'Exiting Vivado' in log
wns=float(re.findall(r'^FULL_PROJECT_WNS ([\d.-]+)',log,re.M)[-1])
whs=float(re.findall(r'^FULL_PROJECT_WHS ([\d.-]+)',log,re.M)[-1])
assert min(wns,whs)>=0
assert 'VIOLATED' not in (reports/'bus_skew.rpt').read_text()
assert re.search(r'nets with routing errors\.+\s*:\s*0', (reports/'route_status.rpt').read_text())
# Guard against accidentally copying an earlier report or mismatched pair.
for name,source in [('TransportPhaseLockFF.bit',ROOT/'TransportPhaseLockFF.runs/impl_1/design_1_wrapper.bit'),
                    ('TransportPhaseLockFF.hwh',ROOT/'TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh')]:
    assert (OUT/name).read_bytes()==source.read_bytes(),name
hwh=ET.parse(OUT/'TransportPhaseLockFF.hwh').getroot()
modules={m.get('FULLNAME'):m for m in hwh.findall('.//MODULE')}
for name in ('/pdh_carrier_frequency','/pdh_modulation_frequency','/photon_counting/axi_dma_3','/photon_counting/axi_gpio_0'):
    assert name in modules,name
for source in ('pdh_tones.py','pdh_tunable_photon.ipynb'):
    shutil.copy2(ROOT/'python_scripts'/source,OUT/source)
shutil.copy2(ROOT/'docs/pdh_tunable_photon.md',OUT/'README.md')
shutil.copy2(ROOT/'build/pdh_direct_tests/results.txt',OUT/'simulation_results.txt')
shutil.copy2(ROOT/'build/pdh_direct_tests/digital_spurs.json',OUT/'digital_spurs.json')
for name,digest in json.loads((OUT/'rtl_checksums.json').read_text()).items():
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name

rows={}
for line in (reports/'utilization.rpt').read_text().splitlines():
    fields=[v.strip() for v in line.split('|')[1:-1]]
    if len(fields)==11 and fields[0] in ('design_1_wrapper','pdh_tones_0','photon_counting'):
        rows[fields[0]]=dict(luts=int(fields[2]),flip_flops=int(fields[6]),
                             bram36=int(fields[7]),bram18=int(fields[8]),uram=int(fields[9]),dsp=int(fields[10]))
for values in rows.values():
    values['bram36_equivalent']=values['bram36']+values['bram18']/2
    values['bram_percent']=values['bram36_equivalent']/1080*100
    values['uram_percent']=values['uram']/80*100
assert rows['pdh_tones_0']['bram36_equivalent']==36
manifest=dict(created_utc=datetime.now(timezone.utc).isoformat(),part='xczu49dr-ffvf1760-2-e',
              feature_version='0x50444803',fabric_clock_hz=245760000,fcw_bits=48,
              slew_fcw_counts_per_clock=1024,setup_slack_ns=wns,hold_slack_ns=whs,
              resources=rows,simulated_photons=9000,rtl_simulation='pass',
              bitstream_generated=True,hardware_programmed=False,project_closed=True)
manifest['sha256']={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in
                     ('TransportPhaseLockFF.bit','TransportPhaseLockFF.hwh','pdh_tones.py','pdh_tunable_photon.ipynb')}
(OUT/'verification.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
