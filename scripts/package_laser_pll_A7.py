"""Package the verified A7 hardware and matching PYNQ helpers; never program a board.

Run after rebuild_laser_pll.tcl exits successfully. Reject stale reports or RTL
changed after the two PLL synthesis runs began.
"""
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
OUT = BUILD / 'laser_pll_overlay'
REPORTS = BUILD / 'full_project'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    freeze = json.loads((BUILD / 'A7_rtl_freeze.json').read_text())
    for name, digest in freeze['files'].items():
        assert sha256(ROOT / name) == digest, f'RTL changed: {name}'
    for index in (0, 1):
        run = ROOT / f'TransportPhaseLockFF.runs/design_1_laser_pll_{index}_0_synth_1'
        assert (run / '.vivado.begin.rst').stat().st_mtime > freeze['timestamp']
        assert (run / '.vivado.end.rst').exists() and not (run / '.vivado.error.rst').exists()
    run = ROOT / 'TransportPhaseLockFF.runs/impl_1'
    assert (run / '.vivado.end.rst').exists() and not (run / '.vivado.error.rst').exists()
    assert 'write_bitstream completed successfully' in (run / 'runme.log').read_text()
    source_bit = run / 'design_1_wrapper.bit'
    source_hwh = ROOT / 'TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh'
    for name, source in [('laser_pll.bit', source_bit), ('laser_pll.hwh', source_hwh)]:
        assert sha256(OUT / name) == sha256(source), f'Export mismatch: {name}'
    for name in ('laser_pll.py', 'laser_pll_loop_sweep.py',
                 'laser_pll_bringup.ipynb', 'laser_pll_loop_sweep.ipynb'):
        assert sha256(OUT / name) == sha256(ROOT / 'python_scripts' / name)
    assert 'FPGA_VERSION = 0xA7' in (OUT / 'laser_pll.py').read_text()

    report_names = ('timing_summary.rpt', 'utilization.rpt', 'drc.rpt',
                    'clock_interaction.rpt', 'pll_setup_paths.rpt', 'pll_hold_paths.rpt')
    for name in report_names:
        assert (REPORTS / name).stat().st_mtime > freeze['timestamp'], f'Stale {name}'
    assert source_bit.stat().st_mtime > (REPORTS / 'timing_summary.rpt').stat().st_mtime
    timing = (REPORTS / 'timing_summary.rpt').read_text()
    table = timing.split('Design Timing Summary', 1)[1]
    values = re.search(r'^\s*(-?\d+\.\d+\s+.*)$', table, re.M).group(1).split()
    setup_ns, hold_ns, pulse_ns = (float(values[k]) for k in (0, 4, 8))
    assert min(setup_ns, hold_ns, pulse_ns) >= 0
    assert all(int(values[k]) == 0 for k in (2, 6, 10))
    assert not re.search(r'\|\s*Error\s*\|', (REPORTS / 'drc.rpt').read_text())
    skew_report = run / 'design_1_wrapper_bus_skew_routed.rpt'
    route_report = run / 'design_1_wrapper_route_status.rpt'
    assert skew_report.stat().st_mtime > freeze['timestamp']
    assert 'VIOLATED' not in skew_report.read_text()
    assert re.search(r'nets with routing errors\.+\s*:\s*0\s*:', route_report.read_text())
    utilization = (REPORTS / 'utilization.rpt').read_text()
    top = next(line for line in utilization.splitlines()
               if re.match(r'\|\s*design_1_wrapper\s*\|', line))
    counts = [int(x.strip()) for x in top.split('|')[3:-1]]
    resources = dict(lut=counts[0], flip_flop=counts[4],
                     bram_36_equivalent=counts[5]+counts[6]/2, dsp=counts[8])

    hwh = ET.parse(OUT / 'laser_pll.hwh').getroot()
    modules = {m.get('INSTANCE') for m in hwh.findall('.//MODULE')}
    addresses = {m.get('INSTANCE'): m.get('BASEVALUE') for m in hwh.findall('.//MEMRANGE')
                 if m.get('MEMTYPE') == 'REGISTER'}
    for prefix in ('pll', 'pll2'):
        for suffix in ('iir', 'iir_feed', 'iir_pole', 'fra_counts', 'fra_extrema', 'fra_samples'):
            assert prefix+'_'+suffix in modules and prefix+'_'+suffix in addresses
    assert {'laser_pll_0', 'laser_pll_1', 'pll2_iq_dma'} <= modules

    (OUT / 'reports').mkdir(exist_ok=True)
    (OUT / 'docs').mkdir(exist_ok=True)
    test_results = json.loads((BUILD / 'A7_tests/results.json').read_text())
    assert len(test_results) == 10 and all(r['status'] == 'pass' for r in test_results.values())
    shutil.copytree(BUILD / 'A7_tests', OUT / 'tests', dirs_exist_ok=True)
    for name in report_names:
        shutil.copy2(REPORTS / name, OUT / 'reports' / name)
    shutil.copy2(skew_report, OUT / 'reports/bus_skew.rpt')
    shutil.copy2(route_report, OUT / 'reports/route_status.rpt')
    for name in ('laser_pll_A7.md', 'laser_pll_rtl_walkthrough.md', 'laser_pll.md'):
        shutil.copy2(ROOT / 'docs' / name, OUT / 'docs' / name)
    for name in freeze['files']:
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    (OUT / 'README.md').write_text(f'''# Laser PLL A7 — {datetime.now():%Y-%m-%d}

Keep laser_pll.bit, laser_pll.hwh, both Python helpers and both notebooks together.
Firmware signature: 0xA7. Hardware has not been programmed. Reloading the bitstream
interrupts existing locks; reloading Python alone does not.

Full-project routed setup/hold/pulse-width slack: {setup_ns:+.3f}/{hold_ns:+.3f}/{pulse_ns:+.3f} ns.
No failing timing endpoints. Existing external-I/O/clock constraint limitations remain.

- Existing loop: ADC 224/3 → DAC 229/1, reference 800 MHz, use `ol`.
- New loop: ADC 225/1 → DAC 229/3, reference 4.4 GHz, use `ol2 = laser_pll.channel(ol, 1)`.
- ADC 225/0 and 225/2 paths and converter rates are preserved.
- Optional independent lead–lag compensators: zero-clock bypass; selected IIR adds
  2–3 clocks, with a 122.88 MS/s update and 24 fractional state bits.
- FRA: longer integration, adaptive complex averaging and separate measured-window
  DAC/internal saturation counts. Contaminated blocks no longer abort a sweep.

Run the bring-up notebook cells individually using the normal board-clock setup.
Acquire lock before the loop-sweep notebook. For a renamed control helper, assign
`fra.laser_pll = laser_pll` after reloading the sweep helper.

The complete two-loop setup, IIR coefficients, register conventions and FRA code
examples are in [the A7 guide](docs/laser_pll_A7.md). Verification and SHA256 checks
are in verification.json. The preserved A6 archive remains in the project build folder.
''')
    manifest = dict(
        date=datetime.now().isoformat(timespec='seconds'), fpga_version='0xA7',
        vivado='2024.1', part='xczu49dr-ffvf1760-2-e', programmed_hardware=False,
        full_board_synthesis_route_bitstream_complete=True,
        setup_slack_ns=setup_ns, hold_slack_ns=hold_ns, pulse_width_slack_ns=pulse_ns,
        setup_failing_endpoints=0, hold_failing_endpoints=0, pulse_width_failing_endpoints=0,
        bus_skew_violations=0, routing_errors=0, bitstream_drc_errors=0,
        resources=resources, fabric_clock_hz=245760000, iir_update_hz=122880000,
        bypass_added_clocks=0, iir_added_clocks=[2, 3], fra_added_clocks=0,
        adc_to_dac_register_clocks_bypass={'stage_0':18, 'stage_2':18, 'stage_3':20, 'stage_4':23},
        default_reference_hz=[800e6, 4.4e9], stage_3_phase_divisor=160,
        iir_state_fraction_bits=24, old_adc225_0_2_paths_preserved=True,
        limitations=['No bench validation of the physical laser or converters.',
                    'Existing clock/external-I/O constraint limitations remain.',
                    'IIR selection is immediate, not a crossfade; dynamic signals can step.',
                    'FRA noise/drift/clipping may bias estimates; inspect repeat quality.'],
        rtl_freeze=freeze, test_results=test_results,
        bd_sha256=sha256(ROOT/'TransportPhaseLockFF.srcs/sources_1/bd/design_1/design_1.bd'),
        register_addresses={k:v for k,v in addresses.items() if k.startswith('pll')},
        tests_passed=['IIR RTL versus floating recurrence, bypass, signed rails and saturation flags',
                      'Actual HLS FRA generator/demodulators, both polarities, clipping and exact counts',
                      'Full PLL ADC tones including 4.3/4.4/4.5 GHz, 18-clock bypass latency',
                      'Acquisition/slip/tracking/DMA regression',
                      '23 control tests; 18 FRA helper tests; both mocked notebooks',
                      'Independent dual PLL/FRA/DMA/IIR BD wiring and preserved old ADC paths'])
    manifest['files'] = {str(p.relative_to(OUT)):sha256(p) for p in sorted(OUT.rglob('*'))
                         if p.is_file() and p.name != 'verification.json'}
    (OUT / 'verification.json').write_text(json.dumps(manifest, indent=2)+'\n')
    shutil.copy2(OUT / 'verification.json', REPORTS / 'verification.json')
    for name, software_only in [('laser_pll_overlay_A7.zip', False), ('laser_pll_A7_python.zip', True)]:
        with zipfile.ZipFile(BUILD/name, 'w', zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(OUT.rglob('*')):
                if p.is_file() and (not software_only or p.suffix in ('.py','.ipynb','.md','.json')):
                    archive.write(p, str(p.relative_to(OUT)))
        with zipfile.ZipFile(BUILD/name) as archive:
            assert archive.testzip() is None
    shutil.copy2(BUILD/'laser_pll_overlay_A7.zip', BUILD/'laser_pll_overlay.zip')
    print(json.dumps({k:manifest[k] for k in ('fpga_version','setup_slack_ns','hold_slack_ns','resources')}, indent=2))
    print('A7 package:', BUILD/'laser_pll_overlay_A7.zip')


if __name__ == '__main__':
    main()
