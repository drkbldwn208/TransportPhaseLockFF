"""Exercise calibrated FF/FB datapath and configuration safety in RTL."""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'build/intensity_linearized/core_test'
BIN=Path('/home/levlabcukomen/tools/Vivado/2024.1/bin')

def run():
    WORK.mkdir(parents=True,exist_ok=True)
    src=ROOT/'TransportPhaseLockFF.srcs/sources_1/new'
    commands=[['xvlog','--sv',str(src/'intensity_compensator.sv'),str(src/'intensity_linearized.sv'),str(ROOT/'tests/intensity_linearized_tb.sv')],
              ['xelab','intensity_linearized_tb','-s','core_sim'],['xsim','core_sim','-runall']]
    for cmd in commands:
        p=subprocess.run([str(BIN/cmd[0]),*cmd[1:]],cwd=WORK,capture_output=True,text=True)
        (WORK/(cmd[0]+'.log')).write_text(p.stdout+p.stderr)
        if p.returncode or 'Fatal:' in p.stdout or 'ERROR:' in p.stdout:
            raise RuntimeError((p.stdout+p.stderr)[-6000:])
    assert 'PASS intensity' in p.stdout
    print(p.stdout[-1200:])
if __name__=='__main__': run()
