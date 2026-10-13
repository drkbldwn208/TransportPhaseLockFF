"""Check 90/800 MHz AM reception with the actual broad PLL FIR coefficients.

The 90 MHz mixer image aliases to 65.76 MHz after decimation. Verify that it
cannot contaminate coherent 60 kHz/960 kHz demodulation over complete windows.
This numerical test covers the physical mixing/filtering, not RTL register delay.
"""
from pathlib import Path
import re
import numpy as np
from scipy.signal import lfilter, freqz
ROOT=Path(__file__).resolve().parents[1]
text=(ROOT/'TransportPhaseLockFF.srcs/sources_1/new/laser_pll_fir_coeffs.vh').read_text()
h=np.array([(-1 if sign else 1)*int(value) for sign,value in re.findall(r'fir_coefficient = (-?)18\'sd(\d+)',text)])[:32]/131072
fs_hz=1_966_080_000.
# 1 ms makes carrier, image, and both modulation frequencies exact cycles.
n=1_966_080
indices=np.arange(n+128)
time_s=indices/fs_hz
for carrier_hz in (90e6,800e6):
 for modulation_hz in (60e3,960e3):
  amplitude=12000*(1+.1*np.sin(2*np.pi*modulation_hz*time_s))
  adc=np.rint(amplitude*np.cos(2*np.pi*carrier_hz*time_s+.7))
  mixed=adc*np.exp(-2j*np.pi*carrier_hz*time_s)
  baseband=lfilter(h,[1],mixed)[128::8]
  t=time_s[128::8]
  sine=np.sin(2*np.pi*modulation_hz*t); cosine=np.cos(2*np.pi*modulation_hz*t)
  i=2*np.mean(baseband.real*sine)+2j*np.mean(baseband.real*cosine)
  q=2*np.mean(baseband.imag*sine)+2j*np.mean(baseband.imag*cosine)
  mean=np.mean(baseband)
  measured=(mean.real*i+mean.imag*q)/(.1*abs(mean)**2)
  expected=np.sum(h*np.exp(-2j*np.pi*modulation_hz*np.arange(32)/fs_hz))
  assert abs(measured-expected)<2e-5,(carrier_hz,modulation_hz,measured,expected)
  print(f'{carrier_hz/1e6:g} MHz carrier, {modulation_hz/1e3:g} kHz AM: |H|={abs(measured):.8f}, phase={np.angle(measured,deg=True):.6f} deg')
print('PASS: both carriers recover FIR amplitude/phase; 90 MHz mixer image rejected by coherent integration')
