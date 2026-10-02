# Four-sample RFDC I/Q derotator

Four signed 16-bit samples per beat on each of the separate I and Q input
and output streams. Each AXI payload is 64 bits: lane 0 is earliest in
bits [15:0], and lane 3 is in bits [63:48]. There is no TLAST or TKEEP.
Connect each output to an `ssr4_fir_decimator` instance.

At a 245.76 MHz fabric clock, each stream carries 983.04 MS/s.
This version preserves the current eight-lane implementation's equations:

```text
I_out = I*cos(phase) + Q*sin(phase)
Q_out = Q*cos(phase) - I*sin(phase)
```

Thus it multiplies I+jQ by exp(-j*phase). The normalized Q1.15 sine LUT,
phase addressing, rounding, and signed 16-bit saturation match the
existing implementation. Rotation can clip full-scale I/Q vectors.

## Frequency and controls

Assuming the same fabric clock, halving the lane count halves the sample
rate. The per-sample FCW is therefore doubled to preserve the original
physical frequency: `2 * 0xF75104D5 mod 2^32 = 0xEEA209AA`.
This is approximately -66.689434 MHz when interpreted as a signed phase
increment at 983.04 MS/s. With the mixer sign above, the applied complex
rotation is approximately +66.689434 MHz.

For another input sample rate or desired frequency, set
`RFDC_IQ_DEROTATOR_4LANE_ROTATION_FCW` in the header using
`round(frequency_Hz / sample_rate_Hz * 2^32) mod 2^32`.

Lane phases are `phase_acc + lane*FCW`; the accumulator advances by
`4*FCW` per accepted beat, modulo 2^32.

- `enable=0` passes samples through exactly while phase keeps advancing.
- `reset_phase=1` starts the accepted beat at `phase_offset`; holding it
  high restarts every beat at that offset.
- `phase_offset` is a 32-bit phase word: `0x40000000` is +90 degrees.

Blocking I/Q stream reads and writes preserve pairing and propagate
backpressure. The design requests II=1. Hardware timing, achieved II,
and resources remain to be checked in synthesis.

## Build

```bash
make csim
make export
make clean
```

`make` defaults to export. Set `VITIS_HLS=/path/to/vitis_hls` if needed.
The target is `xczu49dr-ffvf1760-2-e`, with a 4.069 ns clock constraint.
The top function is `rfdc_iq_derotator_4lane`.

The C testbench checks tone cancellation on all four lanes, exact bypass,
phase continuity through bypass, offsets, repeated reset, wraparound,
and saturation against a floating-point rotation reference. The enabled
mixer comparison allows 48 LSB for LUT/coefficient quantization.

After export, the IP repository is
`rfdc_iq_derotator_4lane_prj/solution1/impl/ip` within this directory.
