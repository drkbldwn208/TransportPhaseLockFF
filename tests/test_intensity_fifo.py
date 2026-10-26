"""Check minimum-rate-divider capture with the actual generated Xilinx FIFO."""
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parents[1]
source=root/'TransportPhaseLockFF.srcs/sources_1/new'
netlist=root/'TransportPhaseLockFF.gen/sources_1/bd/design_1/ip/design_1_intensity_fifo_0/design_1_intensity_fifo_0_sim_netlist.v'
work=root/'build/intensity_fra/fifo_sim';work.mkdir(exist_ok=True)
shutil.copy2(source/'intensity_cosine.mem',work)
bin=Path('/home/levlabcukomen/tools/Vivado/2024.1/bin')
commands=[['xvlog','--sv',str(source/'intensity_tone.sv'),str(source/'intensity_probe.sv'),str(netlist),str(root/'tests/intensity_fifo_tb.sv')],
          ['xelab','-L','unisims_ver','intensity_fifo_tb','glbl','-s','fifo_test'],
          ['xsim','fifo_test','-runall']]
for args in commands:
    r=subprocess.run([str(bin/args[0]),*args[1:]],cwd=work,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (work/(args[0]+'.log')).write_text(r.stdout)
    if r.returncode or 'Fatal:' in r.stdout:raise RuntimeError(r.stdout[-7000:])
assert 'PASS:' in r.stdout
print(next(line for line in r.stdout.splitlines() if line.startswith('PASS:')))
