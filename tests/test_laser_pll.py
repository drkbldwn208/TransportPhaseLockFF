"""Run actual RTL in Vivado xsim against real-tone/floating-point references.

Usage: python3 tests/test_laser_pll.py
Artifacts are retained under /tmp/laser_pll_test (override with PLL_TEST_DIR).
"""
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
from scipy.signal import firwin, freqz

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'TransportPhaseLockFF.srcs/sources_1/new'
WORK = Path(os.environ.get('PLL_TEST_DIR', '/tmp/laser_pll_test'))
BIN = Path(os.environ.get('VIVADO_BIN', '/home/levlabcukomen/tools/Vivado/2024.1/bin'))
FS = 1_966_080_000.0
TURN = 1 << 48
PHASE = 1 << 18


def signed(x, bits):
    return (int(x) + (1 << (bits-1))) % (1 << bits) - (1 << (bits-1))


def wrap(x):
    return (x + np.pi) % (2*np.pi) - np.pi


def run():
    WORK.mkdir(exist_ok=True, parents=True)
    for filename in ('laser_pll_sine.mem', 'laser_pll_hann.mem'):
        shutil.copy(SRC / filename, WORK)
    h = firwin(32, 120e6, fs=FS, window=('kaiser', 7))
    hq = np.rint(h * 131072).astype(int)
    hq[15:17] += (131072-hq.sum())//2
    h = hq / 131072
    scenarios = [
        ('phase', 800e6, 20000, .7, False),
        ('amplitude_low', 800e6, 2000, .7, False),
        ('quadrant_2', 800e6, 18000, 2.6, False),
        ('quadrant_3', 800e6, 18000, -2.6, False),
        ('capture_plus100', 900e6, 20000, .1, True),
        ('capture_minus100', 700e6, 20000, .1, True),
        ('capture_plus100_maxgain', 900e6, 20000, .1, True),
        ('capture_minus100_maxgain', 700e6, 20000, .1, True),
        ('phase_inverted', 800e6, 20000, .7, False),
        ('phase_offset', 800e6, 20000, .7, False),
        ('phase_wrap', 817e6, 18000, -.2, False),
        ('zero_signal', 800e6, 0, 0, False),
        ('amplitude_modulation', 800e6, 15000, .7, False),
    ]
    vectors=[]; expected={}; nco_expected=[]; acc=0; fcw=0; ack=0
    cycle=0
    for name, fin, amplitude, initial_phase, capture in scenarios:
        history=np.zeros(32,dtype=complex)
        for local in range(650):
            reset = local >= 3
            valid = local >= 5
            word = round(800e6/FS*TURN)
            high=(word>>32) | (1<<16)
            maxgain = name.endswith('maxgain')
            ctrl=(64<<16) | ((15 if maxgain else 6)<<8) | ((15 if maxgain else 0)<<4)
            ctrl |= (int(capture)<<1) | int(local>=5) | (int(name=='phase_inverted')<<2)
            offset=round(.5/(2*np.pi)*PHASE) if name=='phase_offset' else 0
            indices=np.arange(8)+8*local
            a=amplitude
            if name=='amplitude_modulation': a *= 1+0.65*np.sin(2*np.pi*1e6*indices/FS)
            adc=np.rint(a*np.cos(2*np.pi*fin/FS*indices+initial_phase)).astype(int)
            packed=sum((int(v)&0xffff)<<(16*k) for k,v in enumerate(adc))
            phases=np.array([((acc+k*fcw)%TURN)/TURN for k in range(8)])
            iq=adc*np.exp(-2j*np.pi*phases)
            history=np.concatenate((history[8:],iq))
            filtered=np.dot(h,history[::-1])
            if 80 < local < 625:
                expected[cycle+15]=(name, offset*2*np.pi/PHASE-np.angle(filtered), fin-800e6, capture, amplitude)
            vectors.append(f'{int(reset):x} {int(valid):x} 1 {packed:032x} {word&0xffffffff:08x} {high:08x} {ctrl:08x} {offset:x}\n')
            if not reset: acc=fcw=ack=0
            else:
                acc=(acc+8*fcw)%TURN
                if (high>>16)&1 != ack: fcw=word;ack=1
            nco_expected.append((acc,fcw)); cycle+=1

    # Frequency update with partial register writes: stage low, then commit high.
    # Also exercise data gaps, explicit phase restart, disable and DAC backpressure.
    old_word=word; new_word=round(801e6/FS*TURN)
    for k in range(180):
        low=new_word&0xffffffff if k>=10 else old_word&0xffffffff
        high=(old_word>>32)|(1<<16) if k<30 else new_word>>32
        if k>=90: high=(new_word>>32)|(1<<16)|(1<<17)
        valid=not 45<=k<50
        ready=not 60<=k<65
        ctrl=(64<<16)|1 if k<80 else 64<<16
        vectors.append(f'1 {int(valid):x} {int(ready):x} {0x33333333333333333333333333333333:032x} {low:08x} {high:08x} {ctrl:08x} 0\n')
        acc=(acc+8*fcw)%TURN
        if (high>>16)&1 != ack:
            fcw=((high&0xffff)<<32)|low;ack=(high>>16)&1
            if high & (1<<17): acc=0
        nco_expected.append((acc,fcw));cycle+=1
    (WORK/'stimulus.txt').write_text(''.join(vectors))
    sources=[str(SRC/f'laser_pll{x}.sv') for x in ('_mixer','_fir','_cordic','_unwrap','_phase_scale','_error','_fft','_handoff','_acquisition','')]
    sources.append(str(SRC/'laser_pll_dac.v'))
    fft_wrapper = ROOT/'TransportPhaseLockFF.srcs/sources_1/ip/laser_pll_fft_core/sim/laser_pll_fft_core.vhd'
    if not fft_wrapper.exists():
        fft_wrapper = ROOT/'TransportPhaseLockFF.gen/sources_1/ip/laser_pll_fft_core/sim/laser_pll_fft_core.vhd'
    commands=[['xvhdl',str(fft_wrapper)], ['xvlog','--sv','-i',str(SRC),*sources,str(ROOT/'tests/laser_pll_tb.sv')],
              ['xelab','-L','xfft_v9_1_12','laser_pll_tb','-s','laser_pll_sim'], ['xsim','laser_pll_sim','-runall']]
    for command in commands:
        p=subprocess.run([str(BIN/command[0]),*command[1:]],cwd=WORK,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (WORK/f'{command[0]}.txt').write_text(p.stdout)
        if p.returncode: raise RuntimeError(p.stdout[-7000:])
    rows=(WORK/'output.txt').read_text().splitlines()
    errors={}; freq_errors={}; checked=0
    for row in rows:
        c,p,f,d,acc_read,word_read=row.split();c=int(c)
        p=int(p,16); f=signed(int(f,16),32); d=signed(int(d,16),16)
        assert (int(acc_read,16),int(word_read,16))==nco_expected[c], f'Phase continuity cycle {c}'
        if c not in expected: continue
        name, angle, delta_hz, capture, amplitude=expected[c]
        if amplitude==0:
            assert not p&(1<<19), 'No phase should be valid for zero input'
            assert d==0, 'Zero input must mute DAC'
            continue
        assert p&(1<<19), f'Missing valid phase {c}'
        error=wrap(signed(p,18)*2*np.pi/PHASE-angle)
        errors.setdefault(name,[]).append(error)
        # DDS quantization, ADC quantization and finite CORDIC precision.
        assert abs(error)<0.0015, (c,name,error)
        measured_hz=f*(FS/8)/PHASE
        freq_errors.setdefault(name,[]).append(measured_hz+delta_hz)
        assert abs(measured_hz+delta_hz)<100000, (name,measured_hz,delta_hz)
        # DAC has three additional registers beyond phase_status; check the
        # actual arithmetic, not just the phase probe, to measure its latency.
        dc=signed(int(rows[c+3].split()[3],16),16)
        if capture:
            assert dc==(-32768 if delta_hz>0 else 32767), (name,dc)
        else:
            polarity=-1 if name=='phase_inverted' else 1
            assert dc==(polarity*signed(p,18))//4, (name,dc,signed(p,18)//4)
        checked+=1
    for name,err in errors.items():
        print(f'{name}: max phase error {max(abs(np.array(err)))*1e6:.1f} urad; max frequency error {max(abs(np.array(freq_errors[name]))):.0f} Hz')
    print(f'PASS: {checked} phase samples; +/-100 MHz capture polarity; zero-signal mute; coherent/staged DDS updates; AXIS packing/stalls')
    print('ADC word -> DAC register latency: 18 clocks = 73.24 ns; FIR group delay: 7.884 ns (converter latency excluded).')
    print(f'Artifacts: {WORK}')


if __name__=='__main__':
    run()
