"""Check acquisition state, handoff continuity and bounded phase memory in RTL."""
from pathlib import Path
import os
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'TransportPhaseLockFF.srcs/sources_1/new'
WORK=Path('/tmp/laser_pll_acquisition_test')
BIN=Path(os.environ.get('VIVADO_BIN','/home/levlabcukomen/tools/Vivado/2024.1/bin'))


def run():
    WORK.mkdir(exist_ok=True)
    sources=[SRC/f'laser_pll_{name}.sv' for name in ('unwrap','phase_scale','error','handoff','acquisition')]
    commands=[['xvlog','--sv',*map(str,sources),str(ROOT/'tests/laser_pll_acquisition_tb.sv'),str(ROOT/'tests/laser_pll_fine_entry_tb.sv'),str(ROOT/'tests/laser_pll_phase_scale_tb.sv')],
              ['xelab','laser_pll_phase_scale_tb','-s','phase_scale_sim'],
              ['xsim','phase_scale_sim','-runall'],
              ['xelab','laser_pll_acquisition_tb','-s','acquisition_sim'],
              ['xsim','acquisition_sim','-runall'],
              ['xelab','laser_pll_fine_entry_tb','-s','fine_entry_sim'],
              ['xsim','fine_entry_sim','-runall']]
    for command in commands:
        result=subprocess.run([str(BIN/command[0]),*command[1:]],cwd=WORK,text=True,
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (WORK/f'{command[0]}_{command[1]}.txt').write_text(result.stdout)
        if result.returncode or 'Fatal:' in result.stdout: raise RuntimeError(result.stdout[-5000:])
        if command[0]=='xsim':
            assert 'PASS:' in result.stdout
            print(next(line for line in result.stdout.splitlines() if line.startswith('PASS:')))
    assert 'PASS:' in result.stdout


if __name__=='__main__': run()
