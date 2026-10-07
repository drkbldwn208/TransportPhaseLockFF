"""End-to-end acquisition with actual ADC tones, PLL RTL and AMD FFT model."""
from pathlib import Path
import os
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'TransportPhaseLockFF.srcs/sources_1/new'
WORK=Path('/tmp/laser_pll_stages_test')
BIN=Path(os.environ.get('VIVADO_BIN','/home/levlabcukomen/tools/Vivado/2024.1/bin'))


def run():
    WORK.mkdir(exist_ok=True)
    for name in ('sine','hann'):
        shutil.copy(SRC/f'laser_pll_{name}.mem',WORK)
    wrapper=ROOT/'TransportPhaseLockFF.gen/sources_1/ip/laser_pll_fft_core/sim/laser_pll_fft_core.vhd'
    if not wrapper.exists():
        wrapper=ROOT/'TransportPhaseLockFF.srcs/sources_1/ip/laser_pll_fft_core/sim/laser_pll_fft_core.vhd'
    sources=[SRC/f'laser_pll{name}.sv' for name in
             ('_mixer','_fir','_cordic','_unwrap','_error','_fft','_handoff','_acquisition','')]
    commands=[['xvhdl',str(wrapper)],
              ['xvlog','--sv','-i',str(SRC),*map(str,sources),str(SRC/'laser_pll_dac.v'),str(ROOT/'tests/laser_pll_stages_tb.sv')],
              ['xelab','-L','xfft_v9_1_12','laser_pll_stages_tb','-s','stages_sim'],
              ['xsim','stages_sim','-runall']]
    for command in commands:
        result=subprocess.run([str(BIN/command[0]),*command[1:]],cwd=WORK,text=True,
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (WORK/f'{command[0]}.txt').write_text(result.stdout)
        if result.returncode or 'Fatal:' in result.stdout:
            raise RuntimeError(result.stdout[-5000:])
    assert 'PASS:' in result.stdout
    print(next(line for line in result.stdout.splitlines() if line.startswith('PASS:')))


if __name__=='__main__': run()
