"""RTL checks for acquired-phase gain ramps and finite, nonblocking I/Q capture."""
from pathlib import Path
import os
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'TransportPhaseLockFF.srcs/sources_1/new'
WORK=Path('/tmp/laser_pll_tracking_test')
BIN=Path(os.environ.get('VIVADO_BIN','/home/levlabcukomen/tools/Vivado/2024.1/bin'))


def run():
    WORK.mkdir(exist_ok=True)
    for name in ('tracking','monitor'):
        top=f'laser_pll_{name}_tb'
        commands=[['xvlog','--sv',str(SRC/f'laser_pll_{name}.sv'),str(ROOT/f'tests/{top}.sv')],
                  ['xelab',top,'-s',top],['xsim',top,'-runall']]
        for command in commands:
            result=subprocess.run([str(BIN/command[0]),*command[1:]],cwd=WORK,text=True,
                                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            (WORK/f'{name}_{command[0]}.txt').write_text(result.stdout)
            if result.returncode or 'Fatal:' in result.stdout:
                raise RuntimeError(result.stdout[-6000:])
        assert 'PASS:' in result.stdout
        print(next(line for line in result.stdout.splitlines() if line.startswith('PASS:')))


if __name__=='__main__': run()
