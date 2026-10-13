"""Regression: an intact AXIS drawing can still have disconnected scalar pins."""
from pathlib import Path
from copy import deepcopy
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_intensity_servo import GENERATED, check_connections, verify

hwh = ET.parse(GENERATED / 'hw_handoff/design_1.hwh').getroot()
verify()
# Reproduce each half of the R8 fault independently, retaining the interface
# metadata. Either scalar override must be rejected even if the other is good.
for signal in ('tdata', 'tvalid'):
    disconnected = deepcopy(hwh)
    adc = next(m for m in disconnected.findall('.//MODULE')
               if m.get('INSTANCE') == 'usp_rf_data_converter_0')
    pin = next(p for p in adc.findall('./PORTS/PORT') if p.get('NAME') == 'm01_axis_' + signal)
    pin.set('SIGNAME', 'orphan_adc_' + signal)
    try:
        check_connections(disconnected)
    except AssertionError:
        pass
    else:
        raise AssertionError('Missed orphan ADC ' + signal)

print('PASS: regenerated intensity path connected; orphan data and valid each rejected')
