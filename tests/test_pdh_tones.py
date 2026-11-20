"""RTL sample-level check of both DAC rates, tone amplitudes and reference phase."""
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
    block, frame, sum_hex, ref_hex = line.split()
    block, frame = int(block), (int(frame)-4) % 512
    summed = unpack(sum_hex,14)
    ref = unpack(ref_hex,8)
    ac,as_,rc,rs = settings[block]
    t = (frame+np.arange(14)/14)/245.76e6
    phi = 2*np.pi*60e6/245.76e6*(frame+np.arange(8)/8)
    expected = np.floor((np.rint(32767*np.cos(2*np.pi*1.2e9*t))*ac+
                         np.rint(32767*np.cos(2*np.pi*60e6*t))*as_+16384)/32768)
    expected_ref = np.floor((np.rint(32767*np.cos(phi))*rc+np.rint(32767*np.sin(phi))*rs+16384)/32768)
    assert np.max(abs(summed-expected)) == 0, (block,frame,'sum')
    assert np.max(abs(ref-expected_ref)) == 0, (block,frame,'reference')
    records[block].append((frame,summed))
# Gen3 RFDC x2 interpolation: AMD PG269 FIR1a, symmetric 59 taps.
# Normalize for gain two after inserting zeros. Model assumes steady periodic
# input and exact arithmetic; analog DAC SFDR is outside this digital test.
half = [5,0,-17,0,44,0,-96,0,187,0,-335,0,565,0,-906,0,1401,0,
        -2112,0,3145,0,-4723,0,7415,0,-13331,0,41526]
h = np.array(half+[65536]+half[::-1])/65536
results = []
for block, rows in enumerate(records):
    samples = np.concatenate([wave for frame,wave in sorted(rows,key=lambda p:p[0])])
    spectrum = 2*np.fft.rfft(samples)/len(samples)
    ac,as_,_,_ = settings[block]
    # Full 512-clock period: 7168 samples, bins 2500 and 125.
    assert abs(spectrum[2500]-ac*32767/32768)<0.1
    assert abs(spectrum[125]-as_*32767/32768)<0.1
    spectrum[[2500,125]]=0
    spur = max(abs(spectrum))
    assert spur<1, 'Unexpected coherent spur above one 16-bit fabric LSB'
    upsampled = np.zeros(2*len(samples)); upsampled[::2]=samples
    filtered = np.fft.ifft(np.fft.fft(upsampled)*np.fft.fft(h,len(upsampled))).real
    dac_spectrum = 2*abs(np.fft.rfft(filtered))/len(filtered)
    # The x2 filter must preserve desired tones while rejecting both images.
    for frequency_hz, amplitude in ((1.2e9,ac),(60e6,as_)):
        index = round(frequency_hz/(6.88128e9/len(filtered)))
        if amplitude:
            assert abs(dac_spectrum[index]/amplitude-1)<0.001
            image_index = len(samples)-index
            image_dbc = 20*np.log10(dac_spectrum[image_index]/dac_spectrum[index])
            assert image_dbc < -80, (frequency_hz,image_dbc)
    results.append(dict(block=block, max_pl_spur_dbfs=20*np.log10(spur/32767)))
print(results)
print('PASS: 2048 frames; exact samples in all lanes, 1.2 GHz and 60 MHz, reference phase; digital RFDC x2 filter images below -80 dBc')
