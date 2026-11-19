"""Bundle the verified PDH build with its matching PYNQ controls and notebooks."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/PDH_1200_60'


def main():
    log = (OUT / 'host_console.log').read_text()
    if not re.search(r'^PDH_BITSTREAM_COMPLETE ', log, re.M):
        raise RuntimeError('Finish the routed build and bitstream before packaging.')
    timing = (OUT / 'reports/timing_summary.rpt').read_text()
    match = re.search(r'WNS\(ns\).*?\n\s*-+.*?\n\s*([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)\s+([-\d.]+)', timing, re.S)
    if not match:
        raise RuntimeError('Could not read routed setup/hold/pulse-width results.')
    wns_ns, whs_ns, wpws_ns = (float(match.group(i)) for i in (1, 5, 9))
    assert min(wns_ns, whs_ns, wpws_ns) >= 0
    pdh_slacks = re.findall(r'Slack \(MET\)\s*:\s*([\d.]+)ns', (OUT / 'reports/pdh_setup.rpt').read_text())
    pdh_setup_slack_ns = min(map(float, pdh_slacks))

    # Retain the existing optical-loop and intensity notebooks and their inputs.
    previous = ROOT / 'build/intensity_IS03_PLL640_R7'
    for old in previous.iterdir():
        if old.suffix in ('.py', '.ipynb'):
            source = ROOT / 'python_scripts' / old.name
            if old.name == 'laser_pll_R7.py':
                source = ROOT / 'python_scripts/laser_pll.py'
            shutil.copy2(source, OUT / old.name)
    for name in ('pdh_tones.py', 'pdh_tones.ipynb'):
        shutil.copy2(ROOT / 'python_scripts' / name, OUT / name)
    for name in ('docs', 'intensity_servo_20261028'):
        shutil.copytree(previous / name, OUT / name, dirs_exist_ok=True)
    shutil.copy2(ROOT / 'docs/pdh_tones.md', OUT / 'docs/pdh_tones.md')
    pdh_doc = OUT / 'docs/pdh_tones.md'
    pdh_doc.write_text(pdh_doc.read_text().replace('../python_scripts/pdh_tones.ipynb', '../pdh_tones.ipynb'))
    shutil.copy2(ROOT / 'docs/blacs_intensity_servo_handoff.md', OUT / 'docs/blacs_intensity_servo_handoff.md')
    (OUT / 'tests').mkdir(exist_ok=True)
    for name in ('xvlog.log', 'xelab.log', 'xsim.log', 'python_tests.log', 'phase_fra_notebook.log'):
        shutil.copy2(ROOT / 'build/pdh_tests' / name, OUT / 'tests' / name)

    (OUT / 'README.md').write_text(f'''# PDH summed tones, retaining R7 PLLs and IS03 intensity servo

Use `TransportPhaseLockFF.bit` and its matching `.hwh` together. This build
drives DAC229/2 with 1.2 GHz + 60 MHz and DAC228/2 with a phase-adjustable
60 MHz reference. Start with `pdh_tones.ipynb`; the frequency plan and register
map are in [docs/pdh_tones.md](docs/pdh_tones.md).

The default 60 MHz/carrier voltage ratio is 0.587654. `set_levels(ol)` uses
carrier amplitude 0.55, sideband amplitude about 0.3232, reference 0.10.
Hardware reset and `configure(ol)` default to zero output. Digital amplitudes
are not calibrated EOM volts; calibrate sideband powers and reference phase.
DAC229/2's RFDC mixer must be **630 MHz**, as configured by the helper.

Both feedback PLLs, the /640 secondary-PLL range, intensity servo, calibration,
shot capture and closed-loop FRA remain. RF-chain FRA and DAC228/2's former
GPIO/DMA tone path are replaced. Use the updated `laser_pll_phase_fra.py`;
`mode='closed'` works, while `mode='rf'` is rejected before hardware writes.
The PLL firmware byte is still A7. PDH feature ID is 0x50444801; the phase-FRA
feature ID is now 0x52463702.

Full routed timing: WNS {wns_ns:+.3f} ns, WHS {whs_ns:+.3f} ns, WPWS
{wpws_ns:+.3f} ns. Reports and test logs are included. No board was programmed;
analog spectra, relative phase and EOM behavior still require bench checks.
This directory is independent of the user's `pynq_overlays/` export monitor.
''')
    verification = dict(
        release='PDH-1200-60-R7-IS03-PLL640',
        wns_ns=wns_ns, whs_ns=whs_ns, wpws_ns=wpws_ns,
        pdh_setup_slack_ns=pdh_setup_slack_ns,
        programmed_hardware=False,
        default_sideband_voltage_ratio=1.081979112658792/1.8411848682178047,
        connectivity=json.loads((OUT / 'connectivity_check.json').read_text()),
        sha256={}, source_sha256={},
    )
    source_dir = ROOT / 'TransportPhaseLockFF.srcs/sources_1/new'
    sources = list(source_dir.glob('pdh_*')) + [source_dir / 'laser_pll.sv', source_dir / 'laser_pll_wrapper.v',
        ROOT / 'TransportPhaseLockFF.srcs/sources_1/bd/design_1/design_1.bd']
    for path in sorted(sources):
        verification['source_sha256'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.suffix in ('.bit', '.hwh', '.ltx', '.py', '.ipynb', '.md'):
            verification['sha256'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT / 'verification.json').write_text(json.dumps(verification, indent=2)+'\n')
    with zipfile.ZipFile(OUT.with_name(OUT.name+'_python.zip'), 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.rglob('*')):
            relative = path.relative_to(OUT)
            if path.is_file() and (relative.parts[0] in ('docs', 'intensity_servo_20261028', 'reports', 'tests') or
                                  (len(relative.parts) == 1 and path.suffix in ('.py', '.ipynb', '.md', '.json'))):
                archive.write(path, relative)
    print('Packaged:', OUT)


if __name__ == '__main__':
    main()
