> Superseded by the direct parallel LUT implementation in `docs/pdh_tunable_photon.md`.
> These candidate files are not in the active Vivado project.

# Tunable PDH tone generator: RTL outline

Status: isolated candidate, 2026-11-23. None of these files is added to the
open Vivado project, and the existing PDH RTL, block design, helper and bitstream
are unchanged. This is a tested datapath/control outline, not a finished overlay.

## Signals and implementation

Keep the existing clocks, RFDC mixers in bypass, and interpolation factors:

| Output | Fabric samples / 245.76 MHz clock | Fabric sample rate | RFDC DAC rate |
|---|---:|---:|---:|
| DAC230/0: carrier + 60 MHz | 14 real samples | 3.44064 GS/s | 6.88128 GS/s |
| DAC228/2: 60 MHz reference | 8 real samples | 1.96608 GS/s | 3.93216 GS/s |

```text
48-bit carrier phase -> shared sine/cosine -> 14 amplitude-weighted rotations --+
                                                                            +--> sum / round --> DAC230/0
60 MHz common phase  -> shared sine/cosine -> 14 amplitude-weighted rotations --+
                                      \--> 8 rotations, including LO phase ------> DAC228/2

inactive coefficient registers -- commit --> phase-word bank tag
                                             travels through sine/cosine pipeline
                                             selects matching coefficient bank
```

There are two phase sources, not independent oscillators per sample lane.
For a carrier phase Phi at the first sample of a word, lane k is

`Ac * cos(Phi + k*delta) = cos(Phi)*Cc[k] + sin(Phi)*Cs[k]`,

where `delta = 2*pi*FCW/2^48`, `Cc = Ac*cos(k*delta)`, and
`Cs = -Ac*sin(k*delta)`. The carrier accumulator advances by `14*FCW` each
fabric clock. FCW resolution is 12.2236 microhertz at 3.44064 GS/s. The reference
uses the same 60 MHz phase as the added tone, but different sample-time offsets
because it has eight rather than fourteen samples per word.

The rotations are exact trigonometric identities, not small-angle expansions.
Their correctness does not depend on slow frequency ramps. Slow ramps simply
allow software to prepare new coefficients between updates. No sine/cosine
state is recursively multiplied from one sample to the next, avoiding cumulative
rotation-rounding drift.

## Modules

- `pdh_phase_source.sv`: the 48-bit carrier phase accumulator, exact 125/512-turn
  60 MHz increment, and conversion into signed CORDIC scaled-radian inputs.
- `pdh_parallel_rotations.sv`: 72 signed 24-by-18 multiplications, pairwise sums,
  carrier/modulation addition, one final rounded/saturated 16-bit output per lane.
  The reference has a matching pipeline delay. Amplitude is included in the
  coefficients, so no separate gain multipliers are needed.
- `pdh_tunable_outline.sv`: two coefficient banks, word-write/commit interface,
  bank tags, phase sources, rotation datapath, and sticky fault mute.
- `coefficients.py`: pure Python calculation of frequency increment and all
  coefficients. This does not write GPIOs, restart clocks, or program hardware.

The two sine/cosine engines are external ports in the outline. This makes
the missing IP integration explicit rather than substituting a private CORDIC
implementation for the vendor core.

## Sine/cosine backend choices

For AMD CORDIC v6.0, use two identical `Sin_and_Cos` cores, parallel architecture,
maximum pipelining, coarse rotation, nonblocking flow and nearest-even rounding.
Input width 26, scaled radians, gives **24 effective phase bits per full turn**:
the 26-bit signed value is angle/pi with 23 fractional bits. Output width 24
gives signed Q22 sine/cosine. Enable synchronous active-low reset and a one-bit
phase-channel TUSER. Pass `phase_bank` through both cores' TUSER and connect
their returned tags to `carrier_bank` and `modulation_bank`.

AXIS phase data is byte-padded to 32 bits; sign-extend the 26-bit input. With
24-bit output width the Cartesian output is 48 bits: cosine in bits 23:0,
sine in bits 47:24. Both engines must have identical latency and accept one
sample per fabric clock. A word-serial CORDIC cannot meet that throughput even
though long pipeline latency is acceptable. These requirements follow
[AMD PG105](https://www.amd.com/content/dam/xilinx/support/documents/ip_documentation/cordic/v6_0/pg105-cordic.pdf).

An economical alternative is two identical dual-port quarter-wave tables,
each storing 512 intervals of 18-bit sine values and 9-bit differences.
Ten fractional address bits allow linear interpolation. Sine and cosine use
the two read ports. Each engine uses one BRAM36 and two interpolation
multipliers, with fewer logic/register resources than a pipelined CORDIC.
Its Q17 output can be shifted left five bits to match the Q22 rotation interface.
The numerical model includes this backend; its RTL is not included yet.

## Frequency changes and coefficient bank lifetime

`configuration_words()` prepares a complete configuration. The logical word
interface is intentionally separate from AXI/GPIO wiring:

| Word | Meaning |
|---|---|
| 0 | Low 32 bits of phase increment per fabric word |
| 1 | High 16 bits of phase increment per fabric word |
| 2 | Bit 0 summed output enable; bit 1 reference enable |
| 3 | Reserved, do not write |
| 4..31 | Fourteen carrier coefficient pairs, cosine then negative sine |
| 32..59 | Fourteen added 60 MHz coefficient pairs |
| 60..75 | Eight reference coefficient pairs, including reference phase |

Each coefficient occupies the low 18 bits, signed two's complement, in units
of DAC amplitude counts times four. There are 72 coefficients in a bank.
Use a memory-mapped register adapter later; do not create dozens of GPIO IPs.

1. Wait for `cfg_busy=0`.
2. Write words 0, 1, 2, and 4..75 to the inactive bank with `cfg_write`.
3. Pulse `cfg_commit` separately from the last write.
4. The bank and frequency increment change together. The phase accumulator
   advances through the old sample word before taking the new slope, with no
   phase reset. Outputs continue at their normal rate.
5. The bank tag travels through CORDIC with its phase. Coefficients are selected
   only when that word reaches the rotation multipliers.
6. `cfg_busy` stays asserted until the first new-bank word reaches those
   multipliers. The old bank can then safely be overwritten: its last products
   are already registered.

An incomplete configuration, write during busy, missing/misaligned CORDIC word,
output stall, or arithmetic clip sets a sticky fault and mutes both outputs.
Reset is the only fault-clear mechanism in this outline. A production wrapper
still needs the normal software version/status interface and rearm operation.
Python validates carrier range and amplitude headroom; a production wrapper
should also decide which corresponding hardware configuration checks to expose.

Pipeline after sine/cosine: multiplication -> pairwise add -> tone sum/reference
alignment -> rounded DAC register. Phase sources keep running while muted.
The coefficient enable bits are delayed with the data. Frequency updates are
delayed by the same pipeline, rather than flushing or stalling it. Physical
reference phase still includes RFDC, filter and cable delay and needs calibration.

## Resource estimate

Device totals: 1,080 BRAM36 equivalents, 4,272 DSP48, 425,280 LUTs, 850,560 FFs.
Counts below cover both outputs, including the 60 MHz reference.

| Scheme | BRAM36 equivalents | Device BRAM | Multiplication DSPs | Device DSP |
|---|---:|---:|---:|---:|
| Current fixed-period PDH (routed) | 11 | 1.02% | 44 | 1.03% |
| Direct replicated LUT, 14-bit phase address, 16-bit samples | 36 | 3.33% | 36 | 0.84% |
| Shared interpolated tables + rotations | 2 | 0.19% | about 76 | 1.78% |
| Two shared CORDICs + rotations, this outline | 0 waveform BRAM | 0% | about 72 | 1.69% |

Each 24-by-18 rotation product fits one DSP48E2. There are four products per
summed-output lane and two per reference lane: `14*4 + 8*2 = 72`.
The DSP counts are arithmetic estimates; synthesis can pack adders differently.
The two coefficient banks alone require 2,592 FFs (0.305% of device FFs), not
BRAM. There are additional phase, pipeline, validity and control registers.

CORDIC is not free logic: its shift/add stages consume LUTs and FFs, not DSPs.
AMD's published parallel 32-bit Sin_and_Cos examples use roughly 3,500 LUTs
and 3,600 FFs per core and zero DSP/BRAM. The planned 26-in/24-out cores should
be smaller, but an exact total has not been synthesized. As a conservative
planning allowance, reserve roughly 10,000 LUTs (2.35%) and 15,000 FFs (1.76%)
for the complete CORDIC-based generator including control and rotations; these
are allowances, not measured utilization. The interpolated-table option avoids
most of the CORDIC logic cost. See
[AMD CORDIC resource examples](https://download.amd.com/docnav/documents/ip_attachments/cordic.html).

Compared with the current whole-design totals, replacing only PDH with the
CORDIC outline would make BRAM about 26.76% and multiplier-DSP usage about
10.02% (currently 27.78% and 9.36%). Routing/timing cannot be inferred from
these percentages. No synthesis or full-project timing claim is made here.

## Numerical spectra and spur locations

Run `python3 scripts/analyze_pdh_tunable.py`. Results and a near-carrier plot
are under `build/pdh_tunable_analysis/`. This models finite phase precision,
18-bit rotation coefficients, and final 16-bit fabric-word rounding. It is
NOT the AMD bit-accurate CORDIC model and excludes RFDC interpolation/rounding,
the physical DAC, clock phase noise, RF amplification, and EOM nonlinearities.

At 1.2 GHz with carrier amplitude 0.55 and the default 60 MHz ratio:

- The 24-iteration reference CORDIC model's strongest spur within +/-10 MHz is
  at **+8.16 MHz, -122.7 dBc**. This is not a hardware SFDR specification.
- Rotation-coefficient images occur at `fold(fc + m*245.76 MHz, 3.44064 GHz)`,
  where fold maps a discrete-time frequency to 0..1.72032 GHz. Examples for
  fc=1.2 GHz include 954.24, 1,257.60 and 1,445.76 MHz. Their locations are far
  from the carrier here, but this is not true at every tuning frequency.
- Folded carrier images approach the carrier near fc = 860.16, 983.04,
  1,105.92 and 1,228.80 MHz. For example at **983.0409375 MHz**, a spur appears
  **1.875 kHz below the carrier at -111.6 dBc**, mainly from rotation/output
  precision. Increasing only CORDIC width will not remove that contribution.
- The 60 MHz rotation stream has images including 797.28, 923.04, 1,043.04,
  1,168.80 and 1,288.80 MHz. Tuning the carrier near one of these puts that
  otherwise distant image close to it. The model puts these at low levels;
  these calculations do not explain any earlier large measured spurs.

The sampled frequency cases are snapped to a 937.5 Hz FFT grid to avoid carrier
leakage. Only the carrier and intended 60 MHz bin are excluded; the closest
resolved offset is 937.5 Hz. This is a set of example configurations, not a
worst-case proof for every 1 Hz frequency word or very close-in noise.

Ramps add a different mechanism: periodic frequency updates can leave lines at
the update frequency and harmonics relative to an ideal linear chirp. For
midpoint-held frequency steps at update rate fu and slope r in Hz/s, the first
small-signal phase-modulation amplitude is approximately `r/(pi*fu^2)` radians,
with first sideband amplitude `r/(2*pi*fu^2)` relative to the carrier after
dechirping. At r=100 kHz/s this is about -36 dBc for fu=1 kHz and -76 dBc for
fu=10 kHz. These are examples, not assumptions about the experiment. Phase
continuity alone does not guarantee a spur-free staircase ramp. A future
hardware ramp sequencer is optional if software update timing proves limiting.

## Validation and remaining integration

`python3 tests/test_pdh_tunable_outline.py` compiles the isolated RTL with Xsim
and a behavioral, rounded sine/cosine replacement for the external IP. It checks
726 sample words across 0.8 GHz, 1.2 GHz, 1.200001 GHz and 1.3 GHz; reference
phases 150, 330, -90 and 0 degrees; phase continuity; coefficient-bank updates;
and DAC stall mute. Maximum error against the physical cosine formula was
0.746 DAC counts. This validates the outline's sequencing and arithmetic, not
the numerical accuracy or timing of the eventual vendor CORDIC instance.

Still required before a bitstream: choose and instantiate the sine backend,
add/register-map the AXI interface and software feature ID, run vendor-IP
simulation and synthesis, close the user's project before BD changes, then
run full timing implementation and measure the RF spectrum on the board.
