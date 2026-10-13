"""Compare lead/lag RTL with its floating-point physical recurrence and phasor."""
from pathlib import Path
import subprocess
import os
import numpy as np
from scipy.signal import lfilter
ROOT=Path(__file__).resolve().parents[1]
BIN=Path('/home/levlabcukomen/tools/Vivado/2024.1/bin')
WORK=Path('/tmp/laser_pll_iir_test')

def run():
    WORK.mkdir(exist_ok=True)
    for command in (['xvlog','--sv',os.environ.get('IIR_SOURCE',str(ROOT/'TransportPhaseLockFF.srcs/sources_1/new/laser_pll_iir.sv')),str(ROOT/'tests/laser_pll_iir_tb.sv')],
                    ['xelab','laser_pll_iir_tb','-s','iir'],['xsim','iir','-runall']):
        p=subprocess.run([str(BIN/command[0]),*command[1:]],cwd=WORK,capture_output=True,text=True)
        (WORK/(command[0]+'.log')).write_text(p.stdout+p.stderr)
        if p.returncode or 'Fatal:' in p.stdout: raise RuntimeError((p.stdout+p.stderr)[-5000:])
    assert 'PASS:' in p.stdout
    phase,x,y,valid,saturated=np.loadtxt(WORK/'iir_trace.txt').T
    # phase=0 samples the ADC code; phase=1 emits that sample's recursive result.
    previous_raw=np.r_[-1234,x[:-1]]
    samples=((x+previous_raw)/2)[phase==0]
    actual=y[phase==1]
    b=[268435456/2**27,-267093279/2**27]; a=[1,-2126008800/2**31]
    expected=lfilter(b,a,samples)
    count=min(len(actual),len(expected))
    error=actual[2000:count]-expected[2000:count]
    assert np.max(np.abs(error))<0.52, np.max(np.abs(error))
    assert not np.any(saturated[4000:])
    print('PASS: lead/lag float recurrence <0.52 DAC code error; bypass/overflow RTL checks')
if __name__=='__main__': run()
