"""Check physical RF I/Q amplitude/phase and AXIS packing in the new source."""
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'TransportPhaseLockFF.srcs/sources_1/new'
WORK=Path('/tmp/laser_pll_rf_pm_test');WORK.mkdir(exist_ok=True)
BIN=Path('/home/levlabcukomen/tools/Vivado/2024.1/bin')
shutil.copy2(SRC/'laser_pll_sine.mem',WORK/'laser_pll_sine.mem')
for command in (['xvlog','--sv',str(SRC/'laser_pll_rf_pm.sv'),str(ROOT/'tests/laser_pll_rf_pm_tb.sv')],
                ['xelab','laser_pll_rf_pm_tb','-s','rf_pm'],['xsim','rf_pm','-runall']):
    result=subprocess.run([str(BIN/command[0]),*command[1:]],cwd=WORK,capture_output=True,text=True)
    (WORK/(command[0]+'.log')).write_text(result.stdout+result.stderr)
    if result.returncode or 'Fatal:' in result.stdout:raise RuntimeError((result.stdout+result.stderr)[-4000:])
assert 'PASS: RF PM quadrants' in result.stdout
print('PASS: RF PM quadrants, 0/full/clamped amplitude, constant envelope, idle identity, packing and stalls')
