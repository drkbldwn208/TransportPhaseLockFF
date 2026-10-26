"""RTL simulation of diagnostic injection, capture integrity and the one-clock command boundary."""
from pathlib import Path
import subprocess
import shutil

root=Path(__file__).resolve().parents[1]
src=root/'TransportPhaseLockFF.srcs/sources_1/new'
work=root/'build/intensity_fra/sim'
work.mkdir(parents=True,exist_ok=True)
bin=Path('/home/levlabcukomen/tools/Vivado/2024.1/bin')
shutil.copy2(src/'intensity_cosine.mem',work)
commands=[['xvlog','--sv',str(src/'intensity_tone.sv'),str(src/'intensity_probe.sv'),str(root/'tests/intensity_probe_tb.sv')],
          ['xelab','intensity_probe_tb','-s','intensity'],['xsim','intensity','-runall']]
for command in commands:
    result=subprocess.run([str(bin/command[0]),*command[1:]],cwd=work,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (work/(command[0]+'.log')).write_text(result.stdout)
    if result.returncode or 'Fatal:' in result.stdout:raise RuntimeError(result.stdout[-6000:])
assert 'PASS:' in result.stdout
print(next(line for line in result.stdout.splitlines() if line.startswith('PASS:')))
