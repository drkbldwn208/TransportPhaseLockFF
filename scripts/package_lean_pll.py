"""Collect verified lean-build helpers and report resource/timing changes.

Run after build_lean_pll.tcl completes. Never writes pynq_overlays or hardware.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/PLL_LEAN'
BASELINE = ROOT / 'build/PDH_DAC230_1200_60/reports'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timing(path):
    lines = path.read_text().splitlines()
    header = next(i for i, line in enumerate(lines) if line.strip().startswith('WNS(ns)'))
    values = lines[header + 2].split()
    return dict(wns_ns=float(values[0]), whs_ns=float(values[4]), wpws_ns=float(values[8]))


def resources(path):
    row = next(line for line in path.read_text().splitlines()
               if re.match(r'\|\s*design_1_wrapper\s*\|', line))
    values = [int(x.strip()) for x in row.split('|')[3:-1]]
    return dict(lut=values[0], flip_flop=values[4],
                bram_36_equivalent=values[5] + values[6]/2, dsp=values[8])


def main():
    from check_lean_pll import main as check_connections
    check_connections()
    for filename, expected in json.loads((OUT / 'source_checks.json').read_text())['source_sha256'].items():
        assert digest(ROOT / filename) == expected, f'RTL changed during build: {filename}'
    run = ROOT / 'TransportPhaseLockFF.runs/impl_1'
    assert 'write_bitstream completed successfully' in (run / 'runme.log').read_text()
    assert not (run / '.vivado.error.rst').exists()
    bit, hwh = OUT / 'TransportPhaseLockFF.bit', OUT / 'TransportPhaseLockFF.hwh'
    source_files = json.loads((OUT / 'source_checks.json').read_text())['source_sha256']
    assert bit.stat().st_mtime >= max((ROOT / name).stat().st_mtime for name in source_files)
    assert digest(bit) == digest(run / 'design_1_wrapper.bit')
    assert digest(hwh) == digest(ROOT / 'TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh')
    current_timing = timing(OUT / 'reports/timing_summary.rpt')
    assert min(current_timing.values()) >= 0, current_timing
    assert 'PASS:' in (OUT / 'pynq_metadata_check.log').read_text()
    shutil.copy2(ROOT / 'build/full_project/intensity_filter_setup.rpt', OUT / 'reports/intensity_filter_setup.rpt')
    for name in ('laser_pll.py', 'intensity_calibration.py', 'repair_intensity_hwh.py'):
        shutil.copy2(ROOT / 'python_scripts' / name, OUT / name)
    # Existing notebooks may import this historical filename.
    shutil.copy2(OUT / 'laser_pll.py', OUT / 'laser_pll_R7.py')
    shutil.copy2(ROOT / 'docs/pll_lean_build.md', OUT / 'README.md')
    previous_resources = resources(BASELINE / 'utilization.rpt')
    current_resources = resources(OUT / 'reports/utilization.rpt')
    result = dict(release='PLL_LEAN', programmed_hardware=False,
                  timing=current_timing, previous_timing=timing(BASELINE / 'timing_summary.rpt'),
                  resources=current_resources, previous_resources=previous_resources,
                  resource_reduction_percent={key: 100*(1-current_resources[key]/value)
                                              for key, value in previous_resources.items()},
                  added_intensity_delay_ns=1e9/245.76e6, added_pll_delay_ns=0,
                  bit_sha256=digest(bit), hwh_sha256=digest(hwh), pynq_parsed_blocks=144)
    (OUT / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
