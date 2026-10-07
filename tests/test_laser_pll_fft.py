"""Exercise the actual AMD xFFT simulation model with raw real ADC tones."""
from pathlib import Path
import os
import shutil
import subprocess
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT/'TransportPhaseLockFF.srcs/sources_1/new'
WORK = Path(os.environ.get('PLL_FFT_TEST_DIR', '/tmp/laser_pll_fft_test'))
BIN = Path(os.environ.get('VIVADO_BIN', '/home/levlabcukomen/tools/Vivado/2024.1/bin'))
FS_HZ = 1_966_080_000.0


def run():
    WORK.mkdir(exist_ok=True, parents=True)
    shutil.copy(SRC/'laser_pll_hann.mem', WORK)
    frequencies_hz = [200e6, 201e6, 289.471e6, 500e6, 650e6, 700e6,
                      799e6, 800e6, 800.1e6, 802e6, 900e6, 950e6,
                      0, -1, 50e6, 800e6, 800e6]
    cycles_per_case = 55000
    rng = np.random.default_rng(142)
    with (WORK/'fft_stimulus.txt').open('w') as f:
        for case, frequency_hz in enumerate(frequencies_hz):
            n = np.arange(cycles_per_case*8)
            if frequency_hz == 0: samples = np.zeros(n.size, dtype=int)
            elif frequency_hz == -1: samples = np.rint(rng.normal(0, 3000, n.size)).astype(int)
            else:
                amplitude = 64 if case==15 else 12000
                samples = np.rint(amplitude*np.cos(2*np.pi*frequency_hz*n/FS_HZ + 0.37)).astype(int)
                if case==16:
                    # A strong second tone and noise: select the dominant tone.
                    samples += np.rint(6000*np.cos(2*np.pi*350e6*n/FS_HZ)+rng.normal(0,1000,n.size)).astype(int)
            for cycle, row in enumerate(samples.reshape(-1,8)):
                adc = ''.join(f'{int(x)&0xffff:04x}' for x in row[::-1])
                # A gap during processing must reject that frame, then recover.
                valid = not (case==16 and 4500<=cycle<4505)
                f.write(f'{case} {int(cycle>=8):x} {int(valid):x} {adc}\n')
    wrapper = ROOT/'TransportPhaseLockFF.gen/sources_1/ip/laser_pll_fft_core/sim/laser_pll_fft_core.vhd'
    if not wrapper.exists():
        wrapper = ROOT/'TransportPhaseLockFF.srcs/sources_1/ip/laser_pll_fft_core/sim/laser_pll_fft_core.vhd'
    commands = [['xvhdl',str(wrapper)],
                ['xvlog','--sv',str(SRC/'laser_pll_fft.sv'),str(ROOT/'tests/laser_pll_fft_tb.sv')],
                ['xelab','-L','xfft_v9_1_12','laser_pll_fft_tb','-s','fft_sim'],
                ['xsim','fft_sim','-runall']]
    for command in commands:
        result = subprocess.run([str(BIN/command[0]),*command[1:]],cwd=WORK,
                                text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (WORK/f'{command[0]}.txt').write_text(result.stdout)
        if result.returncode: raise RuntimeError(result.stdout[-6000:])
    seen = {case:[] for case in range(len(frequencies_hz))}
    for line in (WORK/'fft_output.txt').read_text().splitlines():
        case,cycle,bin_index,status,peak_power,band_power=line.split()
        case,cycle,bin_index=int(case),int(cycle),int(bin_index)
        status=int(status,16); valid=bool(status & (1<<10))
        assert not status & (3<<12), f'FFT overflow/protocol fault: {line}'
        expected_valid=case not in (12,13,14,15) and not (case==16 and not seen[case])
        assert valid==expected_valid, (line,expected_valid)
        if valid:
            assert abs(bin_index*FS_HZ/1024-frequencies_hz[case])<=FS_HZ/1024, line
        seen[case].append(cycle)
        print(f'{case}: bin {bin_index}, valid={valid}, peak power={peak_power}, cycle={cycle%cycles_per_case}')
    for case, cycles in seen.items():
        assert len(cycles)>=2, (case,cycles)
    period_cycles=seen[0][1]-seen[0][0]
    print(f'PASS: {len(frequencies_hz)} FFT cases; update interval {period_cycles} clocks = {period_cycles/(FS_HZ/8)*1e6:.3f} us')


if __name__=='__main__': run()
