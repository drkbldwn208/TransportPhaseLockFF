"""Actual generated AMD CIC/CORDIC models, not a substitute atan2 calculation."""
from pathlib import Path
import subprocess
import numpy as np
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'TransportPhaseLockFF.srcs/sources_1/new'
GEN=ROOT/'TransportPhaseLockFF.gen/sources_1/bd/design_1/ip'
WORK=ROOT/'build/intensity_filtered/phase_monitor_test';WORK.mkdir(parents=True,exist_ok=True)
BIN=Path('/home/levlabcukomen/tools/Vivado/2024.1/bin')
phases=[0.,.7,np.pi-.03,-np.pi+.03,-1.2]
with (WORK/'input.txt').open('w') as out:
 for _ in range(8):out.write('0 0 0 0 0\n')
 for case,phase in enumerate(phases):
  n=np.arange(65536*4).reshape(-1,4)
  z=9000*np.exp(1j*phase)*(1+np.exp(-2j*np.pi*180e6/983.04e6*n))
  for a,b in zip(np.rint(z.real).astype(int),np.rint(z.imag).astype(int)):
   pack=lambda row:sum((int(v)&65535)<<(16*k) for k,v in enumerate(row))
   out.write(f'{case} 1 1 {pack(a):016x} {pack(b):016x}\n')
names=['design_1_cic_compiler_2_1','design_1_intensity_cal_q_0','design_1_cordic_0_0']
commands=[['xvhdl',*[str(GEN/name/'sim'/(name+'.vhd')) for name in names]],
 ['xvlog','--sv',str(SRC/'intensity_rx_lowpass.sv'),str(SRC/'cordic_average.v'),str(ROOT/'tests/intensity_phase_monitor_tb.sv')],
 ['xelab','-L','cic_compiler_v4_0_18','-L','cordic_v6_0_21','intensity_phase_monitor_tb','-s','phase_sim'],
 ['xsim','phase_sim','-runall']]
# Read library revisions from the generated wrappers instead of assuming an install.
import re
for i,name in enumerate(names):
 text=(GEN/name/'sim'/(name+'.vhd')).read_text()
 lib=re.search(r'LIBRARY ((?:cic_compiler|cordic)_v\w+);',text,re.I).group(1)
 if i==0:commands[2][2]=lib
 if i==2:commands[2][4]=lib
for cmd in commands:
 r=subprocess.run([str(BIN/cmd[0]),*cmd[1:]],cwd=WORK,capture_output=True,text=True)
 (WORK/(cmd[0]+'.log')).write_text(r.stdout+r.stderr)
 if r.returncode or 'Fatal:' in r.stdout:raise RuntimeError((r.stdout+r.stderr)[-5000:])
data=np.loadtxt(WORK/'output.txt')
for case,phase in enumerate(phases):
 rows=data[(data[:,0]==case)&(data[:,1]>8+case*65536+35000)]
 assert len(rows)>=3,(case,len(rows))
 error=np.angle(np.exp(1j*(rows[:,2]/8192-phase)))
 assert max(abs(error))<.001,(phase,error)
 print(f'phase {phase:+.6f} rad: max error {max(abs(error)):.6f} rad, {len(rows)} settled samples')
print('PASS: matched CIC timing and physical phase including +/-pi after 180 MHz image rejection')
