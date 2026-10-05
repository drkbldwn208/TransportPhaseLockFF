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

The frequency is programmable through the `s_axi_control` AXI4-Lite
interface. It is no longer compiled into the IP.

| Byte offset | Register | Format |
| --- | --- | --- |
| `0x10` | `rotation_fcw` | Read/write, signed 32-bit phase increment per complex sample |

Calculate `FCW = round(frequency_hz / sample_rate_hz * 2^32)` and write its
two's-complement bit pattern. Here `frequency_hz` is the input residual
frequency to remove: a +50 kHz input needs a positive FCW, and a -17 MHz
input needs a negative FCW. The resulting shift is **minus** this frequency.
Use the complex sample rate (983.04 MS/s), not the fabric clock or DMA rate.
The frequency resolution is about 0.229 Hz.

The AXI register resets to zero. The streaming block retains `ap_ctrl_none`,
so it runs whenever input is available and requires no start/auto-restart
write. `enable`, `reset_phase`, and `phase_offset` remain external pins.

Lane phases are `phase_acc + lane*FCW`; the accumulator advances by
`4*FCW` per accepted beat, modulo 2^32.
Frequency updates preserve accumulated phase. A zero FCW stops rotation
at the current phase; it does not reset phase or guarantee bit-exact bypass.
Use `enable=0` for exact bypass. Register writes are not synchronized to a
DMA capture boundary; configure before acquisition and allow the downstream
filters to settle.

- `enable=0` passes samples through exactly while phase keeps advancing.
- `reset_phase=1` starts the accepted beat at `phase_offset`; holding it
  high restarts every beat at that offset.
- `phase_offset` is a 32-bit phase word: `0x40000000` is +90 degrees.

Blocking I/Q stream reads and writes preserve pairing and propagate
backpressure. The design requests II=1. Check the synthesis report and
post-route timing when integrating the IP.

## PYNQ example

After integrating the new IP and loading the rebuilt `.bit`/`.hwh` pair:

```python
sample_rate_hz = 983.04e6
residual_frequency_hz = -17.0e6  # Example measured input frequency, I + jQ
fcw = round(residual_frequency_hz / sample_rate_hz * 2**32)
if not -(2**31) <= fcw < 2**31:
    raise ValueError("Frequency must fit the signed FCW range [-Fs/2, Fs/2).")

ip = overlay.rfdc_iq_derotator_4l_0
ip.write(0x10, fcw & 0xFFFFFFFF)
assert ip.read(0x10) == (fcw & 0xFFFFFFFF)
overlay.axi_gpio_13.channel1.write(1, mask=1)  # Apply the programmed rotation
print("Applied frequency shift (Hz):", -fcw * sample_rate_hz / 2**32)
```

For RFDC data already centered at DC, bypass the extra mixer with GPIO
enable zero and use `enable_derotation=False` in the capture helper.
When applying rotation, configure it before capture and use
`enable_derotation=True, toggle_enable=False` to avoid changing mixer
enable after the DMA has already started.

## Build

```bash
make csim
make export
make clean
```

`make` defaults to export. Set `VITIS_HLS=/path/to/vitis_hls` if needed.
The target is `xczu49dr-ffvf1760-2-e`, with a 4.069 ns clock constraint.
The top function is `rfdc_iq_derotator_4lane`.

The C testbench checks tone cancellation for zero, positive, and negative
frequency words on all four lanes, exact bypass, frequency changes without
phase reset (including through bypass and back to zero FCW), offsets,
repeated reset, wraparound, and saturation against a floating-point rotation
reference. The enabled mixer comparison allows 48 LSB for LUT/coefficient
quantization. C simulation checks arithmetic; inspect the generated AXI
register map and use hardware readback to verify integration.

After export, the IP repository is
`rfdc_iq_derotator_4lane_prj/solution1/impl/ip` within this directory.

Refresh the Vivado IP catalog and update the derotator instance. Connect its
new `s_axi_control` slave to a processor AXI-Lite interconnect master and
assign an address. The control interface uses the derotator's `ap_clk` and
`ap_rst_n`; use the interconnect's clock conversion for a different PS AXI
clock domain. Preserve the existing stream and GPIO connections, regenerate
output products, and rebuild the bitstream. Copy the matching `.bit` and
`.hwh` to the target together. HLS export alone does not update the current
Vivado-generated RTL or the running FPGA.
