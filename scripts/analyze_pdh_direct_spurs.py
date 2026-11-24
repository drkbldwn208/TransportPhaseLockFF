"""Steady-frequency digital DDS spectra; excludes RFDC and analog imperfections.

Choose coherent FFT frequencies near requested values to avoid mistaking window
leakage for LUT spurs. FCWs still have the actual 48-bit rounding. No dithering.
"""
from pathlib import Path
import json
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/pdh_direct_tests'
FS_HZ=3.44064e9
N=14*131072
BIN_HZ=FS_HZ/N
phase_mask=np.uint64(2**48-1)
index=np.arange(N,dtype=np.uint64)
wave=np.rint(32767*np.cos(2*np.pi*(np.arange(16384)+.5)/16384)).astype(np.int64)
carrier_gain=round(.55*32767)
modulation_gain=round(.55*(1.081979112658792/1.8411848682178047)*32767)


def tone(frequency_hz):
    fcw=round(frequency_hz/FS_HZ*2**48)
    address=((index*np.uint64(fcw))&phase_mask)>>np.uint64(34)
    return wave[address]


modulation=tone(60e6)
results=[]
for requested_hz in (800e6,1e9,1.2e9,1.2e9+1e6,1.3e9,1_199_940_234.375):
    if requested_hz == 1_199_940_234.375:
        # A 210-kHz phase-grid boundary plus 234.375 Hz brings the first
        # 14-bit truncation spur to 3.84 MHz offset. Resolve it coherently.
        N=14*1048576
        BIN_HZ=FS_HZ/N
        index=np.arange(N,dtype=np.uint64)
        modulation=tone(60e6)
    carrier_bin=round(requested_hz/BIN_HZ)
    frequency_hz=carrier_bin*BIN_HZ
    samples=(carrier_gain*tone(frequency_hz)+modulation_gain*modulation+16384)>>15
    spectrum=abs(np.fft.rfft(samples))
    carrier=spectrum[carrier_bin]
    spectrum[carrier_bin]=0
    spectrum[round(60e6/BIN_HZ)]=0
    spectrum[0]=0
    width=round(10e6/BIN_HZ)
    start,end=carrier_bin-width,carrier_bin+width+1
    peak=start+np.argmax(spectrum[start:end])
    global_peak=np.argmax(spectrum)
    results.append(dict(requested_carrier_hz=requested_hz,simulated_carrier_hz=frequency_hz,
                        fft_bin_hz=BIN_HZ,nearest_resolved_offset_hz=BIN_HZ,
                        worst_within_10mhz_dbc=float(20*np.log10(spectrum[peak]/carrier)),
                        spur_offset_hz=(peak-carrier_bin)*BIN_HZ,
                        worst_global_spur_dbc=float(20*np.log10(spectrum[global_peak]/carrier)),
                        global_spur_hz=global_peak*BIN_HZ))
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'digital_spurs.json').write_text(json.dumps(results,indent=2)+'\n')
for r in results:print(f"{r['simulated_carrier_hz']/1e6:.6f} MHz: near-carrier {r['worst_within_10mhz_dbc']:.1f} dBc at {r['spur_offset_hz']/1e6:+.6f} MHz; global {r['worst_global_spur_dbc']:.1f} dBc")
print('Digital steady-state model only; resolution is listed separately for each case.')
