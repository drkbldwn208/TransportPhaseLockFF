"""Exercise the original HLS cores and recover a known delayed feedback gain."""
from pathlib import Path
import cmath
import os
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'TransportPhaseLockFF.srcs/sources_1/new'
WORK=Path('/tmp/laser_pll_fra_test')
BIN=Path(os.environ.get('VIVADO_BIN','/home/levlabcukomen/tools/Vivado/2024.1/bin'))
HLS=ROOT.parent.parent/'VitisProjects/TransportPhaseLockTransferFunctionMeasurement'


def run():
    WORK.mkdir(exist_ok=True)
    generator=HLS/'Perturbation_gen/perturbation_gen/perturbation_gen/hls/impl/ip/hdl/verilog'
    demod=HLS/'Demod_Err/demod_error/demod_error/hls/impl/ip/hdl/verilog'
    sources=[*generator.glob('*.v'),*demod.glob('*.v'),SRC/'laser_pll_fra.sv',ROOT/'tests/laser_pll_fra_tb.sv']
    for p in generator.glob('*.dat'): shutil.copy2(p,WORK/p.name)
    commands=[['xvlog','--sv',*map(str,sources)],['xelab','laser_pll_fra_tb','-s','fra'],['xsim','fra','-runall']]
    for command in commands:
        result=subprocess.run([str(BIN/command[0]),*command[1:]],cwd=WORK,text=True,
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (WORK/f'{command[0]}.txt').write_text(result.stdout)
        if result.returncode or 'Fatal:' in result.stdout: raise RuntimeError(result.stdout[-7000:])
    assert 'PASS:' in result.stdout
    print(next(x for x in result.stdout.splitlines() if x.startswith('PASS:')))
    for line in (WORK/'fra_sums.txt').read_text().splitlines():
        word,ei,eq,ui,uq=map(int,line.split())
        injection=2*complex(ui-ei,uq-eq)/(16384*32768)
        assert abs(abs(injection)-1024)<0.1, injection
        assert abs(injection.imag)<0.1, injection
        loop=-complex(ei,eq)/complex(ui,uq)
        expected=0.5*cmath.exp(-2j*cmath.pi*(8*word/2**32)*4)
        assert abs(loop-expected)<0.002,(loop,expected)
        print(f'{word*1966080000/2**32:g} Hz: measured L={loop:.6g}; expected {expected:.6g}')

    for line in (WORK/'loopback_sums.txt').read_text().splitlines():
        word,ii,iq,qi,qq,mi,mq=map(int,line.split())
        h_i=2*complex(ii,iq)/(16384*32768*1024)
        h_q=2*complex(qi,qq)/(16384*32768*1024)
        delay=cmath.exp(-2j*cmath.pi*(8*word/2**32)*4)
        assert abs(h_i-2*delay)<0.005,(h_i,2*delay)
        assert abs(h_q-delay)<0.005,(h_q,delay)
        assert abs(mi/16384-8000)<3 and abs(mq/16384+4000)<3
        print(f'Loopback {word*1966080000/2**32:g} Hz: I={h_i}, Q={h_q}; 4-clock delay recovered')

if __name__=='__main__': run()
