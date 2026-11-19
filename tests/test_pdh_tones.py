"""RTL sample-level check of both DAC rates, image amplitudes and reference phase."""
from pathlib import Path
import shutil
import subprocess
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'TransportPhaseLockFF.srcs/sources_1/new'
WORK = ROOT / 'build/pdh_tests'
BIN = Path('/home/levlabcukomen/tools/Vivado/2024.1/bin')
WORK.mkdir(parents=True, exist_ok=True)
for source in SRC.glob('pdh_*.mem'):
    shutil.copy2(source, WORK / source.name)
for command in (
    ['xvlog', '--sv', str(SRC/'pdh_tones.sv'), str(ROOT/'tests/pdh_tones_tb.sv')],
    ['xelab', 'pdh_tones_tb', '-s', 'pdh'], ['xsim', 'pdh', '-runall']):
    result = subprocess.run([str(BIN/command[0]), *command[1:]], cwd=WORK, capture_output=True, text=True)
    (WORK/(command[0]+'.log')).write_text(result.stdout+result.stderr)
    if result.returncode or 'Fatal:' in result.stdout:
        raise RuntimeError((result.stdout+result.stderr)[-5000:])
assert 'PASS: PDH' in result.stdout


def unpack(word, lanes):
    value = int(word, 16)
    words = np.array([(value >> (16*k)) & 65535 for k in range(lanes)], dtype=np.int64)
    return np.where(words >= 32768, words-65536, words)


settings = [(12000,3000,6000,-8000),(0,12000,-10000,0),
            (12000,0,0,-10000),(16000,16000,23000,23000)]
records = [[] for _ in settings]
for line in (WORK/'pdh_samples.txt').read_text().splitlines():
    block, frame, iq_hex, ref_hex = line.split()
    block, frame = int(block), (int(frame)-4) % 1024
    iq = unpack(iq_hex,14)
    ref = unpack(ref_hex,8)
    ac,as_,rc,rs = settings[block]
    theta = 2*np.pi*570e6/245.76e6*(frame+np.arange(7)/7)
    phi = 2*np.pi*60e6/245.76e6*(frame+np.arange(8)/8)
    expected_i = np.floor((np.rint(32767*np.cos(theta))*(ac+as_)+16384)/32768)
    expected_q = np.floor((np.rint(32767*np.sin(theta))*(ac-as_)+16384)/32768)
    expected_ref = np.floor((np.rint(32767*np.cos(phi))*rc+np.rint(32767*np.sin(phi))*rs+16384)/32768)
    assert np.max(abs(iq[::2]-expected_i)) == 0, (block,frame,'I')
    assert np.max(abs(iq[1::2]-expected_q)) == 0, (block,frame,'Q')
    assert np.max(abs(ref-expected_ref)) == 0, (block,frame,'reference')
    records[block].append((frame,iq[::2]+1j*iq[1::2]))
for block, rows in enumerate(records):
    samples=np.concatenate([iq for frame,iq in sorted(rows,key=lambda p:p[0])])
    spectrum=np.fft.fft(samples)/len(samples)
    ac,as_,_,_=settings[block]
    # ±570 MHz -> +1.2 GHz / +60 MHz after the +630 MHz RFDC mixer.
    assert abs(spectrum[2375]-ac*32767/32768)<0.1
    assert abs(spectrum[-2375]-as_*32767/32768)<0.1
    spectrum[[2375,-2375]]=0
    assert max(abs(spectrum))<1, 'Unexpected coherent spur above one DAC code'
print('PASS: 4096 frames, exact samples in all lanes, both sidebands and reference phase; no spur above one code')
