# Summed-tone offset PDH: DAC229/2 and DAC228/2

This build replaces DAC229/2's RF-chain FRA stimulus with an independently
weighted sum of **1.2 GHz and 60 MHz**. DAC228/2 supplies a **60 MHz reference**
with independently programmable amplitude and phase. Both feedback PLLs,
closed-loop phase FRA, intensity servo, calibration and shot capture remain.
DAC228/2's previous GPIO/DMA frequency waveform no longer reaches its output.
RF-chain FRA is unavailable in this build; its helper rejects that mode before
changing hardware. All new outputs reset muted.

## Why sum the RF tones?

For an ideal phase EOM, with angular frequencies Ω = 2π × 1.2 GHz and
ωm = 2π × 60 MHz, the summed voltage gives

```text
Eout = Ein exp[i βc cos(Ωt)] exp[i βm cos(ωm t)].
```

This is also the result of two ideal phase EOMs in series. Optical components
at ωlaser + nΩ + kωm have amplitudes proportional to Jn(βc) Jk(βm), apart from
known phase factors. Every 1.2 GHz optical order receives the same relative
60 MHz sideband pattern.

Phase-modulating the RF carrier instead gives

```text
V(t) ∝ cos[Ωt + α cos(ωm t)]
Eout = Ein exp{i βc cos[Ωt + α cos(ωm t)]}.
```

Its optical components have amplitudes proportional to Jn(βc) Jk(nα).
The original optical carrier has no 60 MHz sidebands, the ±1 orders have
opposite modulation phases, and higher optical orders have modulation index
|nα|. Around the selected +1 order the two schemes can be equivalent for
α = βm; the rest of the optical spectrum differs. Summing reproduces the
existing two-EOM arrangement, provided the amplifier and single EOM pass both
frequencies without significant nonlinearity. This comparison follows directly
from the phase-modulator field and Bessel expansion described in
[Newport's EOM technical note](https://www.newport.com/n/electro-optic-modulator-faqs/p/5511).

## Amplitude targets for an offset PDH lock

For a cavity resonance addressed by the +1.2 GHz optical order, well-resolved
60 MHz sidebands and no nearby unwanted cavity modes, the ideal error slope is
proportional to J1(βc)² J0(βm) J1(βm). Its separate maxima are:

| Quantity | Offset tone | PDH tone |
|---|---:|---:|
| Frequency | 1.2 GHz | 60 MHz |
| Phase modulation index | 1.8412 rad | 1.0820 rad |
| Peak EOM voltage / Vπ at that frequency | 0.5861 | 0.3444 |

Here β = π Vpeak / Vπ; peak-to-peak voltage is twice Vpeak. The offset tone
alone puts 33.86% of total optical power in each first order. At both optimum
indices, the selected +1.2 GHz group contains about 17.95% in its central line
and 7.34% in each adjacent ±60 MHz line. See
[Black's PDH tutorial](https://www.agpohl.physik.uni-mainz.de/files/2023/06/AmJPhys69_79_2001_Black_Intro_PDH.pdf)
for the J0 J1 dependence and the approximately 1.08 rad optimum.

With equal voltage transfer and Vπ at both frequencies, the RF voltage ratio
V60/V1200 is 0.5877, equivalent to −4.62 dB RF power. Digital weights 0.55 and
0.3232 implement that ratio with headroom, but are **not a
calibrated EOM drive setting**. More generally, if Gf is EOM voltage per digital
amplitude at frequency f,

```text
A60/A1200 = 0.5877 × [Vπ(60 MHz)/Vπ(1.2 GHz)] × [G1200/G60].
```

First disable the 60 MHz component and maximize the selected optical first
order. Then increase 60 MHz while measuring PDH slope and optimizing reference
phase. Maximum error slope does not guarantee minimum frequency noise when
residual amplitude modulation, reflected optical background, or RF amplifier
compression matters. The separate reference amplitude should be set for the
demodulator's LO requirement; it does not set optical modulation depth.

## Frequency plan and coherence

No RFDC sample-rate, interpolation, data-width, or tile-clock changes are needed.

| Output | DAC rate | Fabric payload per 245.76 MHz clock | RFDC setting |
|---|---:|---|---|
| DAC229/2 | 6.88128 GS/s | 7 complex I/Q pairs, 16 bits/component | ×4 interpolation, C2R mixer +630 MHz |
| DAC228/2 | 3.93216 GS/s | 8 real 16-bit samples | ×2 interpolation, R2R coarse mixer bypass |

At the 1.72032 GS/s complex input rate, the first output is generated as

```text
I(t) = (Ac + As) cos(2π × 570 MHz × t)
Q(t) = (Ac - As) sin(2π × 570 MHz × t)
```

The RFDC forms I cos(630 MHz t) − Q sin(630 MHz t), giving
Ac cos(1.2 GHz t) + As cos(60 MHz t). The ±570 MHz complex tones fit within
the existing interpolation passband. The separate reference is
Ar cos(60 MHz t + φ). The hardware evaluates each lane at its own sample time;
it does not repeat one 245.76 MS/s sample across the bus.

A shared 10-bit fabric frame counter addresses exact-period waveform ROMs:
570 MHz is 2375 cycles per 1024 fabric clocks and 60 MHz is 250 cycles per
1024 clocks. The +630 MHz RFDC NCO is exactly representable:
630 MHz / 6.88128 GHz = 375/4096. There is no finite tuning-word frequency
error between the intended tones under the existing common-clock setup.

This guarantees the intended nominal frequency relationship, not noiseless or
restart-deterministic analog phase. DAC clock noise, analog delays, RFDC FIFO
latency, and the independently initialized RFDC NCO contribute to the measured
phase. Recalibrate the reference phase after bitstream download, converter
restart, or `configure()`. Ordinary `set_levels()` / `set_reference_phase()`
calls do not reset oscillator phase. Existing RFDC multi-tile synchronization
is not added by this change.

AMD references:

- [RF-DAC mixer equation, NCO, scaling, and synchronization](https://docs.amd.com/r/en-US/pg269-rf-data-converter/RF-DAC-Numerical-Controlled-Oscillator-and-Mixer)
- [RF-DAC interpolation-filter coefficients](https://docs.amd.com/r/en-US/pg269-rf-data-converter/Interpolation-Filter-Details-Gen-3/DFE)

## Python operation

Use the matching bit/HWH, `pdh_tones.py`, and the updated
`laser_pll_phase_fra.py` if using closed-loop FRA. See
[pdh_tones.ipynb](../python_scripts/pdh_tones.ipynb) for the annotated sequence.
Perform the usual RFSoC reference-clock and tile startup first.

```python
import importlib
import pdh_tones as pdh
pdh = importlib.reload(pdh)

# One-time mixer setup; defaults mute amplitudes. Only the two requested
# DAC blocks are changed. Does not download a bitstream or initialize clocks.
print(pdh.configure(ol))

# Example low digital levels for checking both tones and the reference.
print(pdh.set_levels(ol, carrier_amplitude=0.10,
                     reference_amplitude=0.10, reference_phase_deg=0.0))

# Adjust demodulation phase without resetting any oscillator.
pdh.set_reference_phase(ol, 35.0)
print(pdh.status(ol))

# Mute these two outputs only.
pdh.stop(ol)
```

Omitting `sideband_amplitude` uses the default **0.587654 × carrier amplitude**.
`set_levels(ol)` uses carrier 0.55, 60 MHz approximately 0.3232 and reference
0.10. Pass `sideband_amplitude=0` for the carrier-only check, or any explicit
amplitude to override the default ratio. `configure(ol)` still starts with
zero amplitudes, and the hardware resets muted.

Amplitudes are fractions of signed digital full scale, not volts or mW.
Carrier amplitude plus 60 MHz amplitude must be ≤1. Allow practical headroom
for the downstream amplifier and reconstruction filters. The helper refuses
out-of-range amplitudes before writing. Reference amplitude is independent.
Analog gains and DAC reconstruction response affect the physical amplitude
ratio, even though the digital coefficients have the requested ratio.

Never set DAC229/2's mixer to 1.2 GHz with this generator: its required center
is **630 MHz**. Changing it translates both output tones and breaks the 60 MHz
reference relationship. Do not reuse old DAC228/2 frequency-control code.

Coefficient changes commit together, without resetting the shared counter.
They are immediate steps, not a ramp; large phase steps while locked may
disturb the demodulated error. Startup/reset mutes both outputs. A streaming
stall, invalid summed amplitude, or clipping latches a fault and mutes both
outputs once the interfaces can accept zeros. Inspect `status()` and rerun
`configure()` after fixing the cause; recalibrate physical phase after restart.

## RTL blocks, pipeline, and registers

- `pdh_tones_wrapper.v`: Verilog AXIS/GPIO boundary for Vivado block design.
- `pdh_tones.sv`: common frame counter, atomic gain commits, diagnostics, seven
  complex waveform lanes and eight real reference lanes.
- `pdh_offset_0..6.mem`: packed signed cosine/sine at the actual lane times,
  1024 × 32 bits per lane.
- `pdh_reference_0..7.mem`: 60 MHz quadrature basis, 512 × 32 bits per lane.
- `scripts/generate_pdh_rom.py`: reproducible ROM generation.

The generator has four registered stages: ROM read, DSP multiplication,
sum/rounding, and output. Both outputs have the same four-clock digital
pipeline (16.28 ns at 245.76 MHz), excluding RFDC interpolation, FIFO and
analog latency. This adds **no latency to either feedback PLL or the intensity
feedback path**. Amplitude/phase writes affect the coefficient pipeline;
they do not retime other channels.

| IP / address | Offset | Meaning |
|---|---:|---|
| `pdh_control`, 0xA03C0000 | 0 | bit0 sum enable; bit1 reference enable; bit2 commit toggle; bit3 fault-clear toggle |
| `pdh_control` | 8 | bits0/1 active enables; bit2 commit ACK; bit3 invalid amplitude; bit4 summed-output stall; bit5 reference stall; bit6 clip; bit7 reset released |
| `pdh_amplitudes`, 0xA03D0000 | 0 | low16: carrier peak codes; high16: 60 MHz peak codes |
| `pdh_amplitudes` | 8 | low16 signed: Ar cosφ; high16 signed: −Ar sinφ |
| `pdh_version`, 0xA03E0000 | 0 | feature ID 0x50444801 |

Write both coefficient words, then toggle commit. GPIOs and generator share
the fabric clock, so no asynchronous multi-bit transfer is used. The existing
`pll_rf_source` status becomes 0x52463702, identifying closed-loop phase FRA
without the old RF-chain stimulus. The normal PLL version remains 0xA7.

## Verification and build

`tests/test_pdh_tones.py` runs actual RTL in Vivado XSIM and checks every output
sample against the physical waveform, signed I/Q packing, both complex-tone
amplitudes, reference rotation, reset muting, amplitude headroom and stalls.
Its FFT check covers digital quantization spurs; it does not model measured
analog DAC noise or amplifier distortion. `test_pdh_helper.py` checks RFDC
channel isolation and phase-only updates. The phase-FRA regression checks that
closed-loop operation remains available and removed RF mode fails before writes.

`scripts/build_pdh_tones.tcl` validates the BD, synthesizes and routes the whole
project, checks setup/hold timing, and produces a matching bit/HWH/LTX under
`build/PDH_1200_60/`. It does not program the board or copy to `pynq_overlays/`.
Consult the release's reports and verification file for the actual build result;
RTL simulation alone is not a timing signoff or a hardware measurement.

The isolated generator synthesis uses 334 LUTs (0.08% of the device),
370 registers (0.04%), 30 DSP slices (0.70%) and 11 block-RAM tiles (1.02%).
These exclude the GPIO/interconnect addition; routed utilization is reported
separately in the release.

On hardware, first measure each tone separately, then together. Confirm 60 MHz
and 1.2 GHz on DAC229/2 and 60 MHz on DAC228/2. Verify that reference phase rotates
without drift relative to a filtered 60 MHz component of DAC229/2. Then connect
the EOM chain and optimize optical sideband power and PDH slope as above.
