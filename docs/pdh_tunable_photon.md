# Tunable PDH tones and photon histograms

This build replaces the fixed-period PDH waveforms with two direct DDSs. It also
finishes the saved photon-counter block design. The transport PLL, both laser
PLLs, intensity servo, converter rates and their signal paths are preserved.
The earlier shared-CORDIC/rotation outline is not part of this build.

## Tone generation

- DAC230/0: carrier plus modulation tone, 14 real samples per 245.76 MHz clock;
  fabric sample rate 3.44064 GS/s, DAC interpolation ×2, mixer bypass.
- DAC228/2: coherent modulation reference, 8 samples per clock; fabric sample
  rate 1.96608 GS/s, DAC interpolation ×2, mixer bypass.
- Reset frequencies: 1.2 GHz and 60 MHz. Outputs reset muted.
- Carrier command range in Python: 0.8–1.3 GHz. Modulation command range:
  1 Hz–100 MHz. Both use 48-bit frequency control words (FCWs).
- Reference phase and the three amplitudes remain independently adjustable.
  Amplitudes are digital full-scale fractions, not calibrated RF volts.

For **both** oscillators:

```
FCW = round(frequency_hz / 3_440_640_000 * 2**48)
active_FCW moves toward target_FCW by at most 1024 each fabric clock
frame_phase = (frame_phase + 14 * active_FCW) modulo 2**48
main_DAC_phase[k] = frame_phase + k * active_FCW                  k = 0..13
reference_phase[k] = frame_phase + floor(14*k*active_FCW/8)       k = 0..7
```

The reference uses the **same modulation accumulator**, so the unequal sample
rates do not produce relative frequency drift. Interior reference phases round
by less than one 48-bit phase LSB, far below the LUT precision. Every lane in a
frame uses the same frequency snapshot. Phase is never reset by a command,
including a command while muted. Redirecting a ramp is allowed.

“10 bits per clock” is implemented as a **1024-code linear FCW step**, with an
exact final step smaller than 1024 when needed. It is not exponential smoothing.
One FCW LSB is 12.224 microHz; the slope is 3,076,171.875 Hz/s. A 1 MHz move takes
0.3251 s; 100 MHz takes 32.51 s; the full 500 MHz carrier range takes 162.54 s.
The FCW is initialized at the reset frequencies, so startup does not ramp from
zero. The slew rate is currently an RTL constant.

### Small modules and pipeline

| Module | Purpose |
|---|---|
| `gpio_word_cdc.v` | Existing user handshake. Added width/initial-value parameters; original 32-bit/100 defaults are unchanged. |
| `pdh_phase_accumulator.sv` | Slew the 48-bit FCW, integrate phase, calculate parallel sample phases. |
| `pdh_cosine_pair.sv` | Two independent reads from a 4096×16 quarter-wave cosine table. Fold the quadrant and restore the sign. |
| `pdh_tones.sv` | Apply GPIO commits, instantiate the two accumulators and 18 ROM copies, scale/sum samples and handle mute/faults. |
| `pdh_tones_wrapper.v` | Block-design port/interface annotations only. |

Offsets and the frame increment are registered before being added to the frame
phase. The sample path is: lane phase register → quadrant/address register →
BRAM read → sign register → DSP multiply → sum/round register → output register.
There are seven clocks (28.48 ns) from the frame-phase register to DAC-stream
output. This is waveform-generator latency, not added laser-PLL or intensity
feedback latency. FCW updates additionally pass the GPIO handshake and the
registered frequency/offset stages. Output samples use signed 16-bit values;
products are rounded at the final right shift.

The LUT addresses use 14 phase bits per turn (0.02197° bins); values represent bin
centres. Each 4096×16 dual-port table needs two 36-kbit BRAMs. Fourteen copies
supply the carrier and modulation reads; four copies supply eight reference
reads. Expected storage: **36 BRAM36 tiles = 3.333% of 1080 device tiles**, versus
11 tiles (1.019%) for the old fixed-frequency generator. Final implemented totals
and DSP counts are recorded with the build reports. The reproducible table generator is `scripts/generate_pdh_rom.py`. No sample interpolation or
recursive oscillator approximation is used. The 48-bit accumulator controls
frequency precision; it does not give 48-bit sine amplitude/phase accuracy.

### Digital truncation spurs

Direct 14-bit lookup trades memory against phase truncation. This build does not
inherit the earlier CORDIC outline's spur estimates. In the steady-tone numerical
model, the strongest overall truncation spur is about −84 dBc. Usually it is far
from the carrier, but it can move close: the phase grid spacing is
`3.44064 GHz / 16384 = 210 kHz`. Near a multiple of 210 kHz, an offset `delta_f`
can put the first truncation spur roughly `16384 * delta_f` from the carrier
(after sampling aliases). Exactly on the grid, phase truncation is constant and
this particular spur vanishes.

| Simulated carrier | Strongest spur within ±10 MHz | Offset |
|---|---:|---:|
| 800.000625 MHz | -109.9 dBc | -2.561250 MHz |
| 999.999375 MHz | -114.9 dBc | -3.198750 MHz |
| 1200.000000 MHz | -118.9 dBc | +7.680000 MHz |
| 1200.999375 MHz | -114.3 dBc | -5.838750 MHz |
| 1299.999375 MHz | -125.6 dBc | +0.320625 MHz |
| 1199.940234 MHz | -84.3 dBc | -3.840000 MHz |

These are digital predictions with the default summed-tone amplitudes, not
measured analog SFDR or an exhaustive frequency bound. The usual cases use
1.875 kHz FFT bins; the near-grid case uses 234.375 Hz bins. Carrier frequencies
are chosen on an FFT bin to separate spurs from leakage. Quantization in the
RFDC, DAC harmonics, clock phase noise, balun/loading effects and amplifier/EOM
nonlinearity are not included. `scripts/analyze_pdh_direct_spurs.py` reproduces
these results. Larger tables or interpolation would reduce the truncation spurs,
but neither has been added to this requested direct-LUT implementation.

### GPIO words and Python

Feature ID is `0x50444803`; use the accompanying `pdh_tones.py`, not the PDH2 helper.
Addresses are documented for inspection; normal code should use named overlay IPs.

| GPIO | Address | Offset 0 | Offset 8 |
|---|---|---|---|
| `pdh_control` | `0xA03C0000` | enable sum/ref bits 0/1, commit toggle bit 2, clear faults toggle bit 3 | status |
| `pdh_amplitudes` | `0xA03D0000` | carrier amplitude [15:0], modulation amplitude [31:16] | reference amplitude [15:0], phase in 1/65536 turns [31:16] |
| `pdh_version` | `0xA03E0000` | feature ID | — |
| `pdh_carrier_frequency` | `0xA0400000` | FCW [31:0] | FCW [47:32] in low 16 bits |
| `pdh_modulation_frequency` | `0xA0410000` | FCW [31:0] | FCW [47:32] in low 16 bits |

Status retains PDH2 bits 0..7 and adds carrier-ramping bit 8 and
modulation-ramping bit 9. Frequency readbacks are **targets**; they equal the
running frequency once ramping is false. All settings and their commit bit cross
in one bundled handshake. Write data words, then toggle commit and await its
acknowledgement. Intermediate word writes cannot apply a torn FCW.

```python
import importlib, xrfdc
import pdh_tones as pdh
pdh = importlib.reload(pdh)
# Use the normal board-clock initialization and matching bit/HWH first.
print(pdh.configure(ol))  # starts/configures only the two PDH DACs; muted
print(pdh.set_levels(ol, carrier_amplitude=.55,
                     reference_amplitude=.10, reference_phase_deg=150))
fcw = pdh.frequency_word(1_200_001_000.0)
print(pdh.set_fcw(ol, carrier_fcw=fcw))
# Or: pdh.set_frequency(ol, carrier_hz=1_200_001_000.0)
pdh.wait_frequency(ol)
pdh.set_reference_phase(ol, 330)  # same amplitude, sign reversed from 150°
# pdh.stop(ol)  # mutes outputs; does not pause the accumulators
```

The default modulation/carrier amplitude ratio is still 0.587654. The sum of
those two amplitudes must be ≤1. RFDC mode, cable phase, frequency response and
physical RF headroom still require bench verification. In the electrical spectrum
these are two added tones; the EOM produces the optical sideband lattice.

## Photon histogram

The user's hierarchy is retained: `photon_counting`, with `axi_gpio_0`,
`hist_counter_0`, a 4096-word AXIS FIFO, and receive-only `axi_dma_3`.
The GPIO clock and the DMA-to-DDR connection were missing and are now connected.
AXI-lite addresses are `0xA1130000` (DMA) and `0xA1140000` (GPIO). GPIO offset 0
sets the bin count; offset 8 sets clock cycles per bin. Bin duration is
`ncycles / 245.76e6` seconds. Settings latch for the whole shot.

- Photon input: `pmod_photon_counter_pulses`, package pin M14.
- Trigger input: `pmod_photon_counter_trigger`, package pin N14.
- These pins are configured **LVCMOS18**: the detector/trigger must present
  compatible 1.8 V logic; the constraints do not make them 3.3/5 V tolerant.
- Photon pulses pass a two-flop synchronizer, then a rising-edge detector.
  There is no photon debounce/dead-time filter. Detector dead time is an input
  property, not an artificial extra counter dead time.
- Trigger retains the user's five-clock debounce. Use a clean ≥30 ns trigger
  high pulse (100 ns is convenient). Time zero is the accepted synchronized
  trigger, not the raw connector edge. Photon and trigger delays differ;
  calibrate that offset if absolute arrival timing matters. Sampling also gives
  about one clock (4.069 ns) bin-edge uncertainty for asynchronous events.
- First bin starts on the clock after the trigger is accepted. Triggers while
  recording or draining the final word are ignored.
- Output words are unsigned 32-bit bin counts. A finite FIFO cannot absorb an
  indefinitely stalled DMA. Counter output now holds valid data until accepted;
  if a later bin overruns that output, recording stops and emits a final
  `0x80000000` marker. Discard that entire record. Bins are never stretched.
- Allowed `ncycles`: 1..2³¹−1; bin count must be positive. At very short bins,
  the bin-stream data rate, not photon rate, limits DMA recording. Start with
  1 µs or longer bins; 1 µs is about 4 MB/s regardless of photon count rate.
- Arm the receive DMA **before** applying the external trigger. A new shot needs
  a new receive transfer. The 20-bit DMA byte-count field allows ≤262143 bins
  (4 bytes each) per transfer. The notebook validates length and overflow.

## Verification and limits

`tests/test_pdh_direct_photon.py` runs Vivado xsim with the real XPM handshake
model. The DDS test checks every output lane against a separate full-circle
cosine calculation, both ramp directions, final fractional steps, commit
atomicity, phase continuity, reference phases 150°/330°, mute and DAC-stall
faults. The photon test drives the PMOD-level inputs with 9.9 ns pulses at
37.5 MHz and slower irregular spacings, with varying asynchronous starting
phases. A ninth trial alternates 23.3 ns / 30.033 ns intervals (37.5 MHz average),
checking the minimum detector dead time explicitly. All intervals are ≥23.3 ns. It checks counts in every bin, totals,
TLAST, stalls, explicit overflow and repeated/dark records.

For a regular 37.5 MHz train the rising-edge interval is 26.667 ns, longer than 23.3 ns;
the low interval is 16.767 ns. Both high and low exceed two fabric clocks. RTL
simulation tests logical sampling/counting; it does not model analog input
thresholds or metastability probabilities. Full implementation timing and actual
BRAM utilization are checked separately in the Vivado build reports.

The notebook uses the standard [PYNQ simple-DMA driver](https://pynq.readthedocs.io/en/v3.0.0/_modules/pynq/lib/dma.html) for polling, buffer invalidation and received-byte counts.

## Completed build: 23 November 2026

Vivado 2024.1 completed synthesis, placement, routing, post-route checks and
bitstream generation. Full-design setup slack is **+0.059 ns**; hold slack is
**+0.008 ns**. All routed nets are complete, with zero routing errors and no
bus-skew violations. The PDH source's worst setup slack is **+0.591 ns**. The
full design's tightest setup path remains in the existing laser-PLL compensator.
The complete build meets timing, but its overall margin remains small.

| Implemented hierarchy | LUTs | Flip-flops | BRAM36 equivalent | % board BRAM | UltraRAM | DSPs |
|---|---:|---:|---:|---:|---:|---:|
| PDH tones | 4,616 | 3,287 | 36 | 3.33% | 0 | 36 |
| Photon hierarchy, including DMA/FIFO/GPIO | 1,244 | 2,648 | 3 | 0.28% | 1 | 0 |
| Whole design | 76,191 | 95,446 | 328 | 30.37% | 1 | 392 |

The single UltraRAM is **1/80 = 1.25%** of the device's UltraRAM. It implements
the photon stream FIFO; the histogram does not allocate an additional array of
bins in BRAM. Whole-design LUT, flip-flop and DSP usage are respectively 17.92%,
11.22% and 9.18%.

All 9,000 simulated detector pulses were counted, with exact bin totals. The
DDS test checked 2,586 output words across all 22 sample lanes. Twelve Python
helper tests passed, including RFDC channel isolation and mismatched-HWH checks.
The generated-wiring check preserved 293 existing signal nets and all existing
converter/controller parameters and peripheral addresses.

The build contains no DRC errors. Existing warnings and full-design CDC summary
findings remain in the reports; this is not a claim that every legacy crossing
has been redesigned or audited. The new controls use the XPM-backed GPIO
handshake. Simulation does not replace a bench check of input voltage levels,
DAC spectra or metastability reliability. Hardware was not programmed.

Outputs, helper, notebook, reports and SHA-256 manifest are in
`build/PDH_TUNABLE_PHOTON/`. The main project is closed and can be reopened.
The build did not write `pynq_overlays/`; the user's monitor owns that export.
