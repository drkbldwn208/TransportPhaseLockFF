> Current tunable build: see [pdh_tunable_photon.md](pdh_tunable_photon.md).
> The fixed-frequency PDH2 implementation below is retained as historical documentation.

# Summed-tone offset PDH: DAC230/0 and DAC228/2

This build moves the independently weighted **1.2 GHz + 60 MHz** sum to
previously unused **DAC230/0** (PYNQ `dac_tiles[2].blocks[0]`). DAC228/2 remains
the **60 MHz reference**, with programmable amplitude and phase. DAC229/2 now
receives zeros. Both feedback PLLs, closed-loop phase FRA, intensity servo,
calibration and shot capture retain their existing connections and settings.
The old RF-chain FRA and DAC228/2 GPIO/DMA waveform remain unavailable.
All PDH outputs reset muted.

Connect the EOM RF chain to **DAC230/0**, on the ZCU216 JHC3 breakout bank;
keep the PDH demodulator LO on DAC228/2. Match the breakout labels to tile/block,
not just a connector number. [AMD's board connection guide](https://xilinx-wiki.atlassian.net/wiki/spaces/A/pages/767197440/RF+DC+Evaluation+Tool+for+ZCU216+board+-+Quick+start)
identifies JHC3 as the DAC230/231 even-channel bank.

The reported electrical spurs around 1.04–1.29 GHz have **not** been identified
as a specific analog or RFDC fault. This revision removes the complex mixer
translation and uses a different converter. Simulation checks the generated
samples; the bench spectrum is still needed to assess the actual improvement.

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

| Output | DAC rate | Fabric payload per 245.76 MHz clock | RFDC setting |
|---|---:|---|---|
| DAC230/0 | 6.88128 GS/s | 14 real 16-bit samples | ×2 interpolation, R2R coarse bypass |
| DAC228/2 | 3.93216 GS/s | 8 real 16-bit samples | ×2 interpolation, R2R coarse bypass |

DAC230 uses its internal PLL with the **491.52 MHz reference distributed from
DAC229** (`DAC2_Clock_Source=5`). The existing ADC and DAC tiles keep their clock
settings. The new tile does not need a separate external clock cable. Its AXIS
clock is the same ADC225-derived 245.76 MHz clock used by the existing datapath.
The new sample rate matches DAC229 and stays below AMD's 7 GS/s maximum for the
full-Nyquist DUC mode. Higher rates would require a different datapath mode;
this rate comfortably supports 1.2 GHz with the selected ×2 interpolation.

The sum is now generated directly at 3.44064 GS/s:

```text
v(t) = Ac cos(2π × 1.2 GHz × t) + As cos(2π × 60 MHz × t)
r(t) = Ar cos(2π × 60 MHz × t + φ)
```

Both RFDC mixers bypass frequency translation. Each sample lane has its own
correct time coordinate; no scalar sample is repeated across a parallel bus.
A shared 9-bit frame counter addresses exact 512-clock waveform periods:
**2500 cycles at 1.2 GHz** and **125 cycles at 60 MHz**. Both waveforms advance
continuously even when muted. Reference coefficients implement cosφ and −sinφ.

The common clock fixes their nominal frequency relationship. It does not
eliminate analog clock noise or ensure the same physical phase after converter
restart: PLL/FIFO and analog delays differ between tiles. Calibrate reference
phase after a bitstream/converter restart. Live amplitude and phase updates
do not reset the counter or any NCO. Multi-tile synchronization is not added.

The electrical analyzer should show **1.2 GHz and 60 MHz**. It should not show
intentional 1.14/1.26 GHz lines: those are **optical** sidebands generated by the
EOM. The parameter `sideband_amplitude` sets the separate 60 MHz electrical tone.

AMD references:

- [RF-DAC rate limits](https://docs.amd.com/r/en-US/ds926-zynq-ultrascale-plus-rfsoc/RF-DAC-Electrical-Characteristics)
- [RF-DAC datapath modes](https://docs.amd.com/r/en-US/pg269-rf-data-converter/RF-DAC-Datapath-Mode-Gen-3/DFE)
- [Interpolation-filter coefficients](https://docs.amd.com/r/en-US/pg269-rf-data-converter/Interpolation-Filter-Details-Gen-3/DFE)

## Python operation

Use the matching bit/HWH, `pdh_tones.py`, and the updated
`laser_pll_phase_fra.py` if using closed-loop FRA. See
[pdh_tones.ipynb](../python_scripts/pdh_tones.ipynb) for the annotated sequence.
Perform the usual RFSoC reference-clock and tile startup first.

Import `xrfdc` **before constructing `Overlay`**, including an attachment with
`download=False`. PYNQ assigns drivers when it constructs the overlay; importing
`xrfdc` later does not replace an already assigned `DefaultIP`. The notebook
imports the driver first and, if necessary, reattaches to the same running image
without downloading it. For an existing `ol` with the reported `dac_tiles` error:

```python
import xrfdc
from pynq import Overlay
ol = Overlay(ol.bitfile_name, download=False)  # Same matching bit/HWH on disk.
rfdc = ol.usp_rf_data_converter_0
print(type(rfdc))  # Should be xrfdc.RFdc, not pynq.overlay.DefaultIP.
assert hasattr(rfdc, 'dac_tiles'), (ol.ip_dict['usp_rf_data_converter_0']['type'],
                                  xrfdc.RFdc.bindto)
```

This attachment does not download a bitstream or restart clocks/tiles. Do not
rerun clock initialization to fix driver binding. If it remains `DefaultIP`,
compare the printed HWH IP type with `xrfdc.RFdc.bindto` and inspect PYNQ's
warnings; a driver/IP-version mismatch also causes a generic binding.
The helper checks binding before any output writes. See the
[PYNQ Overlay source](https://pynq.readthedocs.io/en/v3.0.0/_modules/pynq/overlay.html)
and [RFDC driver](https://github.com/Xilinx/PYNQ/blob/master/sdbuild/packages/xrfdc/package/xrfdc/__init__.py).

Helper version `2026-11-19.3` requires PDH feature **0x50444802**. The older
helper/bitstream pair is rejected explicitly. `configure()` starts DAC230 if
its startup state is not ready, then configures only DAC230/0 and DAC228/2.
It never restarts the existing tiles. First complete the usual reference-clock
startup so DAC229 can supply the distributed reference.

Both channels now use coarse bypass, so fine-mixer scale and the driver's
shared AUTO-scale flag are irrelevant. The helper checks routing, sample rates,
interpolation and actual coarse bypass settings before enabling output.

```python
import importlib
import pdh_tones as pdh
pdh = importlib.reload(pdh)

# One-time mixer setup; defaults mute amplitudes. Only the two requested
# DAC blocks are changed. Starts the new tile if needed; does not restart existing tiles.
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

Keep both PDH RFDC mixers in **R2R coarse bypass**. Frequencies are generated
in RTL; changing the RFDC NCO is not the tuning mechanism. Do not reuse the old
DAC229/2 630 MHz mixer setup or DAC228/2 frequency-control code.

Coefficient changes commit together, without resetting the shared counter.
They are immediate steps, not a ramp; large phase steps while locked may
disturb the demodulated error. Startup/reset mutes both outputs. A streaming
stall, invalid summed amplitude, or clipping latches a fault and mutes both
outputs once the interfaces can accept zeros. Inspect `status()` and rerun
`configure()` after fixing the cause; recalibrate physical phase after restart.

## RTL blocks, pipeline, and registers

- `pdh_tones_wrapper.v`: Verilog AXIS/GPIO boundary for Vivado block design.
- `pdh_tones.sv`: common frame counter, atomic gain commits, diagnostics, fourteen
  real summed-waveform lanes and eight real reference lanes.
- `pdh_sum_0..13.mem`: packed signed cosines at 1.2 GHz (low 16 bits) and
  60 MHz (high 16 bits), 512 × 32 bits per lane. The old offset ROMs are unused
  and removed from the project file set.
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
| `pdh_version`, 0xA03E0000 | 0 | feature ID 0x50444802 |

Write both coefficient words, then toggle commit. GPIOs and generator share
the fabric clock, so no asynchronous multi-bit transfer is used. The existing
`pll_rf_source` status becomes 0x52463702, identifying closed-loop phase FRA
without the old RF-chain stimulus. The normal PLL version remains 0xA7.

## Verification and build

`tests/test_pdh_tones.py` runs actual RTL in Vivado XSIM and checks every output
sample against the physical waveform, real lane order, both tone
amplitudes, reference rotation, reset muting, amplitude headroom and stalls.
Its FFT check covers digital quantization spurs, and the published RFDC ×2
FIR coefficients check interpolation images. It does not model analog DAC
noise, converter nonlinearities or amplifier distortion. `test_pdh_helper.py` checks RFDC
channel isolation and phase-only updates. The phase-FRA regression checks that
closed-loop operation remains available and removed RF mode fails before writes.

`scripts/build_pdh_tones.tcl` validates the BD, synthesizes and routes the whole
project, checks setup/hold timing, and produces a matching bit/HWH/LTX under
`build/PDH_DAC230_1200_60/`. It does not program the board or copy to `pynq_overlays/`.
The 2026-11-19 DAC230 implementation meets the specified timing constraints:
global setup slack **+0.033 ns**, hold slack **+0.001 ns**, pulse-width slack
**+0.534 ns**, and worst reported path into/out of PDH registers **+0.474 ns**.
All nets are routed and the bus-skew report has no violations. The existing
clock-constraint and BD debug-width warnings remain in the build logs.
Consult the release reports and verification file for details. RTL simulation
and timing analysis do not measure analog DAC spectral purity.

The synthesized generator uses 320 LUTs (0.08%), 369 registers (0.04%),
44 DSP slices (1.03%) and 11 block-RAM tiles (1.02%).
Full routed resources and timing are recorded in the release reports. These
figures exclude GPIOs and interconnect.

On hardware, first measure each tone separately, then together. Confirm 60 MHz
and 1.2 GHz on DAC230/0 and 60 MHz on DAC228/2. Verify that reference phase rotates
without drift relative to a filtered 60 MHz component of DAC230/0. Then connect
the EOM chain and optimize optical sideband power and PDH slope as above.

A practical spur check is: carrier only at amplitude 0.10; 60 MHz only at 0.10;
then both at those same levels. Record spur frequency and dBc in each case.
Repeat with a lower RF level and increased analyzer input attenuation to check
for downstream/analyzer compression. Strong near-carrier spurs are not an
intended feature of the summed waveform. Separate frequency spectra from
phase-coherence checks: compare the filtered 60 MHz component and reference
on two scope channels, then adjust `set_reference_phase()`.
