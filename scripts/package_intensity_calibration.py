"""Package the verified intensity measurement image; preserve earlier releases."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from check_intensity_servo import verify

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/intensity_fra'
OUT = ROOT / 'build/intensity_calibration_R7'
REPORTS = OUT / 'reports'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resources(report, instance):
    line = next(
        line for line in report.splitlines() if re.match(r'\|\s*' + re.escape(instance) + r'\s*\|', line)
    )
    v = [int(x.strip()) for x in line.split('|')[3:-1]]
    return dict(lut=v[0], flip_flop=v[4], bram_36_equivalent=v[5] + v[6] / 2, dsp=v[8])


def main():
    freeze = json.loads((WORK / 'rtl_freeze.json').read_text())
    for name, digest in freeze['files'].items():
        assert sha256(ROOT / name) == digest, f'Source changed after freeze: {name}'
    for name in (
        'design_1_intensity_probe_0_0_synth_1',
        'design_1_laser_pll_0_0_synth_1',
        'design_1_laser_pll_1_0_synth_1',
        'synth_1',
        'impl_1',
    ):
        run = ROOT / 'TransportPhaseLockFF.runs' / name
        assert (run / '.vivado.begin.rst').stat().st_mtime > freeze['timestamp'], f'Stale run: {name}'
        assert (run / '.vivado.end.rst').exists() and not (run / '.vivado.error.rst').exists(), name
    impl = ROOT / 'TransportPhaseLockFF.runs/impl_1'
    assert 'write_bitstream completed successfully' in (impl / 'runme.log').read_text()
    assert sha256(impl / 'design_1_wrapper.bit') == sha256(OUT / 'TransportPhaseLockFF.bit')
    generated = ROOT / 'TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh'
    assert sha256(generated) == sha256(OUT / 'TransportPhaseLockFF.hwh')
    assert (OUT / 'TransportPhaseLockFF.ltx').stat().st_mtime > freeze['timestamp']
    bd_path = ROOT / 'TransportPhaseLockFF.srcs/sources_1/bd/design_1/design_1.bd'
    bd = json.loads(bd_path.read_text())['design']
    previous = json.loads((WORK / 'backup/design_1.bd').read_text())['design']
    assert bd['components']['usp_rf_data_converter_0']['parameters'] == json.loads(
        (WORK / 'rfdc_before.json').read_text()
    )
    # Original controller and setpoint logic remain exactly the same IP/parameters.
    for name in (
        'fast_servo_controller_0',
        'dwell_fcw_streamer_32_0',
        'setpoint_switch_0',
        'sync_axis_power_mod_0',
        'iq_split_0',
        'laser_pll_0',
        'laser_pll_1',
    ):
        for field in ('vlnv', 'parameters'):
            assert bd['components'][name].get(field) == previous['components'][name].get(field), (name, field)
    connection_check = verify()
    hw = ET.parse(generated).getroot()
    addresses = {
        m.get('INSTANCE'): int(m.get('BASEVALUE'), 16)
        for m in hw.findall('.//MEMRANGE')
        if m.get('MEMTYPE') == 'REGISTER'
    }
    old_hw = ET.parse(ROOT / 'build/laser_pll_R7_FRA/laser_pll.hwh').getroot()
    old_addresses = {
        m.get('INSTANCE'): int(m.get('BASEVALUE'), 16)
        for m in old_hw.findall('.//MEMRANGE')
        if m.get('MEMTYPE') == 'REGISTER'
    }
    assert all(addresses.get(k) == v for k, v in old_addresses.items()), 'Existing register address changed'
    for index, name in enumerate(
        ('intensity_control', 'intensity_tone', 'intensity_limits', 'intensity_counts', 'intensity_dma')
    ):
        assert addresses[name] == 0xA0310000 + index * 0x10000, (name, addresses.get(name))
    for prefix in ('pll', 'pll2'):
        for suffix in ('iir', 'fra', 'control'):
            assert prefix + '_' + suffix in addresses
    # PLL1 retains the original shared project's DMA name; PLL2 uses its prefix.
    assert addresses['axi_dma_3'] == 0xA0100000
    assert addresses['pll2_iq_dma'] == 0xA10C0000
    assert addresses['pll_rf_source'] == 0xA0300000
    for name in (
        'timing_summary',
        'utilization',
        'drc',
        'bus_skew',
        'route_status',
        'intensity_servo_routed',
        'intensity_paths',
    ):
        assert (REPORTS / (name + '.rpt')).stat().st_mtime > freeze['timestamp'], f'Stale report: {name}'
    text = (REPORTS / 'timing_summary.rpt').read_text().split('Design Timing Summary', 1)[1]
    values = re.search(r'^\s*(-?\d+\.\d+\s+.*)$', text, re.M).group(1).split()
    setup, hold, pulse = [float(values[k]) for k in (0, 4, 8)]
    assert min(setup, hold, pulse) >= 0 and all(int(values[k]) == 0 for k in (2, 6, 10))
    assert not re.search(r'\|\s*Error\s*\|', (REPORTS / 'drc.rpt').read_text())
    assert 'VIOLATED' not in (REPORTS / 'bus_skew.rpt').read_text()
    assert re.search(r'nets with routing errors\.+\s*:\s*0\s*:', (REPORTS / 'route_status.rpt').read_text())
    routed = (REPORTS / 'intensity_servo_routed.rpt').read_text()
    assert 'PASS: all 64 intensity ADC input bits driven by RFDC' in routed
    pins = re.findall(r'adc_bus\[(\d+)\] <- .*rx0_u_adc/DATA_ADC1\[(\d+)\]', routed)
    assert len(pins) == 64 and len({a for a, b in pins}) == 64
    assert all(int(b) == 32 * (int(a) // 16) + int(a) % 16 for a, b in pins)
    util = (REPORTS / 'utilization.rpt').read_text()
    used = resources(util, 'design_1_wrapper')
    probe = resources(util, 'intensity_probe_0')
    capacity = dict(lut=425280, flip_flop=850560, bram_36_equivalent=1080, dsp=4272)
    old = json.loads((ROOT / 'build/laser_pll_R7_FRA/verification.json').read_text())['resources']
    delta = {k: used[k] - old[k] for k in used}
    tests = {
        'python_tests': ('tests/test_intensity_calibration.py', 'Ran 13 tests'),
        'rtl_tests': ('tests/test_intensity_probe.py', 'PASS: intensity one-clock boundary'),
        'fifo_tests': ('tests/test_intensity_fifo.py', 'PASS: generated Xilinx FIFO reset/rearm'),
        'notebook_tests': ('tests/test_intensity_notebook.py', 'PASS: complete intensity notebook'),
        'connectivity_tests': ('tests/test_intensity_servo.py', 'PASS: regenerated intensity path connected'),
        'dual_bd_tests': ('tests/test_laser_pll_dual_bd.py', 'PASS: independent dual PLL'),
        'pll_control_tests': ('tests/test_laser_pll_control.py', 'Ran 24 tests'),
    }
    (OUT / 'tests').mkdir(exist_ok=True)
    (OUT / 'docs').mkdir(exist_ok=True)
    results = {}
    for name, (script, marker) in tests.items():
        log = WORK / (name + '.log')
        text = log.read_text()
        assert marker in text and not any(bad in text for bad in ('Traceback', 'FAILED', 'Fatal:')), name
        results[name] = dict(
            status='pass', script=script, script_sha256=sha256(ROOT / script), log_sha256=sha256(log)
        )
        shutil.copy2(log, OUT / 'tests' / log.name)
        shutil.copy2(ROOT / script, OUT / 'tests' / Path(script).name)
    shutil.copy2(ROOT / 'tests/intensity_probe_tb.sv', OUT / 'tests/intensity_probe_tb.sv')
    shutil.copy2(ROOT / 'tests/intensity_fifo_tb.sv', OUT / 'tests/intensity_fifo_tb.sv')
    (OUT / 'tests/connectivity.json').write_text(json.dumps(connection_check, indent=2) + '\n')
    for name in (
        'intensity_calibration.py',
        'intensity_calibration.ipynb',
        'laser_pll.py',
        'laser_pll_loop_sweep.py',
        'laser_pll_phase_fra.py',
        'laser_pll_bringup.ipynb',
        'laser_pll_loop_sweep.ipynb',
        'laser_pll_phase_fra.ipynb',
    ):
        shutil.copy2(ROOT / 'python_scripts' / name, OUT / name)
    shutil.copy2(OUT / 'laser_pll.py', OUT / 'laser_pll_R7.py')
    for name in (
        'intensity_calibration.md',
        'laser_pll_A7.md',
        'laser_pll_rf_fra_R7.md',
        'overlay_versions.md',
    ):
        shutil.copy2(ROOT / 'docs' / name, OUT / 'docs' / name)
    for name in freeze['files']:
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    for name in (
        'add_intensity_fra.tcl',
        'build_intensity_fra.tcl',
        'finish_intensity_fra.tcl',
        'build_intensity_fra_incremental.tcl',
        'close_intensity_timing.tcl',
        'check_full_project_timing.tcl',
        'report_laser_pll_timing.tcl',
        'refresh_laser_pll_sources.tcl',
        'check_intensity_servo_routed.tcl',
        'package_intensity_calibration.py',
        'check_intensity_servo.py',
    ):
        target = OUT / 'scripts' / name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(ROOT / 'scripts' / name, target)
    (OUT / 'README.md').write_text(
        f'''# Intensity measurement release — {datetime.now():%Y-%m-%d}

ADC224/1 → existing fast PI → DAC228/3 (80 MHz AOM carrier).
R7 dual laser PLLs, I/Q DMA, phase FRA, intensity LO and 32-bit setpoint path remain.
No live sensor/AOM inverse table. One PI-output boundary register adds 4.069 ns;
the PI arithmetic, gains and integrator behavior are unchanged. L includes this
fixed delay, which is present in both normal and diagnostic operation.

Copy BOTH TransportPhaseLockFF.bit and TransportPhaseLockFF.hwh to the same board
folder, with matching basenames. Copy intensity_calibration.py and
intensity_calibration.ipynb to Jupyter. The included laser PLL helpers remain A7;
intensity measurements use the independent signature 0x494E5401.

Start with intensity_calibration.ipynb. Before downloading, save your working
nonzero manual-setpoint setup using its first cells. Download resets all loops;
the notebook explicitly restores the saved intensity registers/mixers, not the
integrator or other experiment branches. Default attach/reload does not download.

1. Measure raw-sensor counts versus optical power, including dark/offset.
2. Sweep a small actuator dither with feedback active; repeated short records
   give L=-C/U and the calibrated fractional plant K=Q/(P0 U).
3. Compare frequency, amplitude, block duration and capture rate to select a
   quasi-static band; scan and revisit setpoints, bin by actual mean command.
4. Export signed slopes, relative F(u) and the monotonic inverse. This release
   measures and exports only; enabling an inverse in feedback is a later step.

Data saves under intensity_measurements/<timestamp>/ relative to the notebook:
raw NPZ per block, block/aggregate CSVs, setup JSONs, plots, and inverse LUT CSV.
Raw frames are point-decimated, without a new antialias filter. Check sample-rate
convergence. DAC228/3 has no ready signal; ADC invalid gaps are checked, physical
DAC stalls cannot be counted on that interface. See docs/intensity_calibration.md.

Full-board routed setup/hold/pulse slack: {setup:+.3f}/{hold:+.3f}/{pulse:+.3f} ns.
No failing constrained endpoints, routing errors or bitstream DRC errors.
Existing clock/external-I/O constraint limitations remain. Hardware has not been
programmed or optically tested. Full evidence/hashes: verification.json.
'''
    )
    result = dict(
        date=datetime.now().isoformat(timespec='seconds'),
        release='R7-intensity-measurement-1',
        fpga_version='0xA7',
        intensity_feature_version='0x494E5401',
        part='xczu49dr-ffvf1760-2-e',
        vivado='2024.1',
        hardware_programmed=False,
        full_board_synthesis_route_bitstream_complete=True,
        setup_slack_ns=setup,
        hold_slack_ns=hold,
        pulse_width_slack_ns=pulse,
        failing_constrained_endpoints=0,
        routing_errors=0,
        bus_skew_violations=0,
        bitstream_drc_errors=0,
        resources=used,
        intensity_probe_resources=probe,
        resource_change_from_R7_FRA=delta,
        resource_percent_of_device={k: 100 * used[k] / capacity[k] for k in used},
        intensity_probe_percent_of_device={k: 100 * probe[k] / capacity[k] for k in probe},
        feedback_registers_added=1,
        feedback_delay_added_s=1/245.76e6,
        adc_rail_side_path_registers=1,
        pi_algorithm_changed=False,
        live_compensation=False,
        rfdc_parameters_changed=False,
        original_register_addresses_preserved=len(old_addresses),
        measurement=dict(
            adc='224/1',
            dac='228/3',
            lo_dac='228/1',
            fabric_clock_hz=245760000,
            frame_bytes=16,
            raw_i_lanes=4,
            maximum_records=1048575,
            temporal_antialias_filter_added=False,
            tone_ramp_s=64 * 4096 / 245.76e6,
            hardware_dac_stall_detection=False,
            return_ratio='-C/U',
            fractional_plant='Q/(P0*U)',
        ),
        tests=results,
        source_freeze=freeze,
        bd_sha256=sha256(bd_path),
        register_addresses={k: hex(v) for k, v in addresses.items() if k.startswith('intensity')},
        limitations=[
            'No physical AOM/photodetector measurement performed.',
            'Existing clock/external-I/O constraint limitations remain.',
            'Frame decimation aliases out-of-band signals; verify with a second capture rate.',
            'Calibration assumes repeatable F and multiplicative, locally slow incident power.',
        ],
    )
    result['files'] = {
        str(p.relative_to(OUT)): sha256(p)
        for p in sorted(OUT.rglob('*'))
        if p.is_file() and p.name != 'verification.json'
    }
    (OUT / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    for software_only in (False, True):
        path = (
            ROOT
            / 'build'
            / ('intensity_calibration_R7_python.zip' if software_only else 'intensity_calibration_R7.zip')
        )
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(OUT.rglob('*')):
                if p.is_file() and (not software_only or p.suffix in ('.py', '.ipynb', '.md', '.json')):
                    archive.write(p, str(p.relative_to(OUT)))
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
    print(
        json.dumps(
            {
                k: result[k]
                for k in ('setup_slack_ns', 'hold_slack_ns', 'resources', 'intensity_probe_resources')
            },
            indent=2,
        )
    )
    print('Package:', ROOT / 'build/intensity_calibration_R7.zip')


if __name__ == '__main__':
    main()
