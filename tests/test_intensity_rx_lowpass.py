"""Bit-exact RTL and physical checks: DC units, image rejection, bandwidth, gaps.

No optical hardware. The stimulus includes complex downconversion's DC + 2LO
image; the independent integer convolution preserves all coefficient precision.
"""
from pathlib import Path
import json
import subprocess
import numpy as np
from scipy.signal import freqz
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'TransportPhaseLockFF.srcs/sources_1/new'
WORK=ROOT/'build/intensity_filtered/filter_test'
BIN=Path('/home/levlabcukomen/tools/Vivado/2024.1/bin')
H=np.array([243,1423,4698,11113,20616,31342,39982,43310,39982,31342,20616,11113,4698,1423,243],dtype=np.int64)
FS=245.76e6
WORK.mkdir(parents=True,exist_ok=True)
rng=np.random.default_rng(74)
blocks=[]; names=[]
for value in (-32768,-5000,0,5000,32767):
 blocks.append(np.full((128,4),value)+0j);names.append(f'dc_{value}')
for phase in (0.,np.pi-.03,-np.pi+.03):
 n=np.arange(32768*4).reshape(-1,4)
 blocks.append(9000*np.exp(1j*phase)*(1+np.exp(-2j*np.pi*180e6/(4*FS)*n)))
 names.append(f'image_phase_{phase}')
for f in (1e3,1.5e6):
 n=np.arange(32768*4).reshape(-1,4)
 blocks.append(5000+1000*np.exp(2j*np.pi*f/(4*FS)*n));names.append(f'passband_{f}')
blocks.append(rng.integers(-32768,32768,(2048,4))+1j*rng.integers(-32768,32768,(2048,4)));names.append('random_gaps')
expected=[]; rows=[]; ranges={}; offset=0
for name,block in zip(names,blocks):
 vals=np.stack([np.rint(block.real),np.rint(block.imag)],axis=2).astype(np.int64)
 valid=np.ones(len(vals),dtype=int)
 if name=='random_gaps':valid[100:103]=0
 for _ in range(4):rows.append('0 0 0 0\n');expected.append([0,0,0]);offset+=1
 sums=vals.sum(axis=1)*valid[:,None]
 conv=np.stack([np.convolve(sums[:,j],H)[:len(vals)] for j in range(2)],axis=1)
 y=np.zeros_like(conv);y[3:]=(conv[:-3]+2**19)//2**20
 good=np.convolve(valid,np.ones(18,dtype=int))[:len(vals)]==18
 for k,v in enumerate(vals):
  packed=[sum((int(v[lane,j])&65535)<<(16*lane) for lane in range(4)) for j in range(2)]
  rows.append(f'1 {valid[k]} {packed[0]:016x} {packed[1]:016x}\n')
  expected.append([int(good[k]),*y[k]])
 ranges[name]=[offset,offset+len(vals)];offset+=len(vals)
(WORK/'input.txt').write_text(''.join(rows))
for command in [['xvlog','--sv',str(SRC/'intensity_rx_lowpass.sv'),str(ROOT/'tests/intensity_rx_lowpass_tb.sv')],['xelab','intensity_rx_lowpass_tb','-s','fir_sim'],['xsim','fir_sim','-runall']]:
 r=subprocess.run([str(BIN/command[0]),*command[1:]],cwd=WORK,capture_output=True,text=True)
 (WORK/(command[0]+'.log')).write_text(r.stdout+r.stderr)
 if r.returncode or 'Fatal:' in r.stdout:raise RuntimeError((r.stdout+r.stderr)[-5000:])
actual=np.loadtxt(WORK/'output.txt',dtype=int)
assert np.array_equal(actual,np.asarray(expected)),np.argwhere(actual!=expected)[:10]
f,h=freqz(H/2**18,worN=200001,fs=FS);db=20*np.log10(np.maximum(abs(h),1e-15))
assert abs(H.sum()-2**18)==0
assert max(abs(db[f<=1.5e6]))<.035
assert max(db[f>=55e6]) < -86
residuals={}
for name,(a,b) in ranges.items():
 if name.startswith('dc_'):assert np.all(actual[a+64:b,1]==int(name[3:]))
 if name.startswith('image_phase_'):
  z=actual[a+128:b,1]+1j*actual[a+128:b,2];phase=float(name[len('image_phase_'):])
  residuals[name]=float(np.max(abs(z-9000*np.exp(1j*phase))))
  assert residuals[name]<1.6,residuals[name]
  assert abs(np.angle(np.mean(z)*np.exp(-1j*phase)))<1e-4
report=dict(passband_droop_db=float(max(abs(db[f<=1.5e6]))),stopband_max_db=float(max(db[f>=55e6])),
 added_delay_s=11/FS,dc_gain=1.,image_residual_counts=residuals,bit_exact_samples=len(actual))
(WORK/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2));print('PASS: FIR convolution, DC signs/rails, image rejection, +/-pi calibration, valid gaps')
