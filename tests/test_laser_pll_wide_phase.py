"""Run the wide phase range RTL check; no FPGA programming."""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BIN = Path(os.environ.get('VIVADO_BIN', '/home/levlabcukomen/tools/Vivado/2024.1/bin'))
WORK = ROOT/'build/phase_range_20261029/sim_wide_phase'

def run():
    WORK.mkdir(parents=True, exist_ok=True)
    src = ROOT/'TransportPhaseLockFF.srcs/sources_1/new'
    commands = [
        ['xvlog', '--sv', *[str(src/f'laser_pll_{n}.sv') for n in ('unwrap','phase_scale','tracking')],
         str(ROOT/'tests/laser_pll_wide_phase_tb.sv')],
        ['xelab', 'laser_pll_wide_phase_tb', '-s', 'wide_phase_sim'],
        ['xsim', 'wide_phase_sim', '-runall'],
    ]
    for command in commands:
        p = subprocess.run([str(BIN/command[0]), *command[1:]], cwd=WORK,
                           text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (WORK/f'{command[0]}.log').write_text(p.stdout)
        if p.returncode or 'Fatal:' in p.stdout:
            raise RuntimeError(p.stdout[-6000:])
    assert 'PASS:' in p.stdout
    print(next(line for line in p.stdout.splitlines() if line.startswith('PASS:')))

if __name__ == '__main__':
    run()
