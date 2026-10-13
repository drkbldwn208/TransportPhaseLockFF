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
    sources=[*generator.glob('*.v'),*demod.glob('*.v'),SRC/'laser_pll_phase_probe.sv',SRC/'laser_pll_rf_pm.sv',SRC/'laser_pll_fra.sv',ROOT/'tests/laser_pll_fra_tb.sv']
    for p in generator.glob('*.dat'): shutil.copy2(p,WORK/p.name)
    shutil.copy2(SRC/'laser_pll_sine.mem',WORK/'laser_pll_sine.mem')
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

    for line in (WORK/'closed_phase_sums.txt').read_text().splitlines():
        word,pi,pq,ui,uq=map(int,line.split())
        phase=2*complex(pi,pq)/(16384*32768)
        drive=2*complex(ui,uq)/(16384*32768)
        loop=0.5*cmath.exp(-2j*cmath.pi*(8*word/2**32)*4)
        assert abs(phase-4*(drive-1024))<0.8,(phase,4*(drive-1024))
        assert abs((1024-drive)/drive-loop)<0.002
        print(f'Closed phase {word*1966080000/2**32:g} Hz: raw phase agrees with E, U and known loop')
    for line in (WORK/'rf_phase_sums.txt').read_text().splitlines():
        word,pi,pq,di,dq=map(int,line.split())
        response=complex(pi,pq)/complex(di,dq)
        expected=cmath.exp(-2j*cmath.pi*(8*word/2**32)*7)
        assert abs(response-expected)<0.003,(response,expected)
        print(f'RF PM {word*1966080000/2**32:g} Hz: actual DAC I/Q gives {response}; 7-clock RF delay recovered')

if __name__=='__main__': run()
