# RFDC I/Q Derotator HLS IP

This HLS IP takes separate RFDC `I` and `Q` AXI4-Stream inputs, performs a complex derotation, and outputs separate derotated `I` and `Q` AXI4-Stream outputs that can feed standard Xilinx CIC Compiler and FIR Compiler decimation IP.

It is intended to sit after the RFDC, rather than using the RFDC internal mixer, so the existing RFDC pipeline stays unchanged.

## Data Format

Each stream is a 128-bit AXI stream payload containing eight signed 16-bit samples:

```text
bits [15:0]     sample 0
bits [31:16]    sample 1
bits [47:32]    sample 2
bits [63:48]    sample 3
bits [79:64]    sample 4
bits [95:80]    sample 5
bits [111:96]   sample 6
bits [127:112]  sample 7
```

This matches the existing project convention used by `PhaseExtractor.sv`.

The IP has four AXI-stream ports:

```text
s_axis_i  128-bit RFDC I input
s_axis_q  128-bit RFDC Q input
m_axis_i  128-bit derotated I output
m_axis_q  128-bit derotated Q output
```

The HLS payload type is `ap_uint<128>`, so HLS generates plain `TDATA`, `TVALID`, and `TREADY` ports. It does not force `TLAST` or `TKEEP`, which keeps the output easy to connect to Xilinx CIC/FIR IP. If a later DMA path needs packets, add or reuse a TLAST generator after decimation.

## Rotation Frequency

The existing `PhaseAccumulator_8Lane` default FCW is:

```text
0x0B115555
```

That is the 85 MHz word for the 8-lane effective sample rate:

```text
245.76 MHz fabric clock * 8 samples/clock = 1966.08 MS/s
FCW = round(85e6 / 1966.08e6 * 2^32) = 0x0B115555
```

This derotator uses twice that frequency:

```text
rotation FCW = 2 * 0x0B115555 = 0x1622AAAA
```

The phase increment is per sample. Because one AXI beat contains eight time-interleaved samples, lane phases are:

```text
lane 0 phase = bus_start_phase + 0 * rotation_fcw
lane 1 phase = bus_start_phase + 1 * rotation_fcw
...
lane 7 phase = bus_start_phase + 7 * rotation_fcw
```

After one accepted 128-bit bus beat, the internal phase accumulator advances by:

```text
8 * rotation_fcw
```

## Complex Math

Input is treated as:

```text
z = I + jQ
```

To bring the observed negative-phase-ramp tone to baseband, the module
multiplies by:

```text
exp(+j * phase)
```

So the implemented equations are:

```text
I_out = I*cos(phase) - Q*sin(phase)
Q_out = Q*cos(phase) + I*sin(phase)
```

The sine and cosine values are generated with the same quarter-wave lookup
addressing used by the existing RTL `NCO.sv`:

```text
quadrant = phase[31:30]
address  = phase[29:16]
```

The original RTL NCO table is amplitude-scaled for DAC output. The derotator
uses a normalized copy of that table so the mixer coefficients are unit-gain
signed Q1.15 values. This keeps the derotator phase quantization aligned with
the NCO without attenuating the I/Q samples.

The output is clipped back to signed 16-bit samples. That keeps the output stream width compatible with the common CIC/FIR Compiler input setup. If the incoming I/Q vector is near full scale on both axes, rotation can clip because the vector magnitude can exceed the signed 16-bit range.

## Control Inputs

The top function is:

```cpp
void rfdc_iq_derotator(
    hls::stream<axis_iq_bus_t> &s_axis_i,
    hls::stream<axis_iq_bus_t> &s_axis_q,
    hls::stream<axis_iq_bus_t> &m_axis_i,
    hls::stream<axis_iq_bus_t> &m_axis_q,
    bool enable,
    bool reset_phase,
    ap_uint<32> phase_offset);
```

`enable`:

- `1`: derotate.
- `0`: pass I/Q through unchanged.

The internal phase still advances while `enable` is low, so sample-time alignment is preserved if you turn derotation back on.

`reset_phase`:

- Pulse high for one accepted AXI beat to load `phase_offset`.
- If held high, each bus beat restarts from `phase_offset`.

`phase_offset`:

```text
0x00000000 =   0 degrees
0x40000000 =  90 degrees
0x80000000 = 180 degrees
0xC0000000 = -90 degrees
```

This is useful for deterministic captures. You can still do fine residual phase adjustment in post-processing because the output remains full I/Q.

## AXI Handshake Behavior

The module reads one `I` word and one `Q` word, rotates all eight lane pairs, then writes one output word on each output stream.

The two input streams are consumed together. If either input is missing data, the block waits. If either output is backpressured, the block stalls and therefore backpressures both inputs. This preserves I/Q lane alignment.

## CIC/FIR Decimation Chain

A typical chain is:

```text
RFDC I stream -> rfdc_iq_derotator/m_axis_i -> CIC/FIR decimator -> DMA
RFDC Q stream -> rfdc_iq_derotator/m_axis_q -> CIC/FIR decimator -> DMA
```

Use identical decimator settings on I and Q so their group delay and sample timing match. If you use CIC first and FIR compensation second, mirror that exact chain on both streams.

The derotator output stream is AXI4-Stream compatible, but the downstream IP must still be configured for the same sample packing. In this design that means signed 16-bit samples packed eight per 128-bit beat. If a CIC or FIR instance is configured for a single 16-bit sample per beat, insert a serializer/unpacker or configure the IP for the appropriate parallel data path before connecting it directly.

For long phase-noise traces, decimating before DMA is the right move: the RFDC fabric stream is far too wide and fast for multi-second raw captures, but basebanded and decimated I/Q can be captured for much longer windows.

## Sign Check

The implemented direction assumes the measured complex tone has a negative
phase ramp:

```text
I = A*cos(phase)
Q = -A*sin(phase)
```

After derotation, that becomes approximately:

```text
I_out = A
Q_out = 0
```

If the observed tone rotates the opposite direction because of an upstream I/Q convention, use the complex conjugate input convention in software analysis or change the hardware equations back to multiply by `exp(-j*phase)` instead.

## Running HLS

From this directory:

```bash
vitis_hls -f run_hls.tcl
```

The script:

1. runs C simulation,
2. synthesizes for `xczu49dr-ffvf1760-2-e`,
3. uses a 4.069 ns clock constraint for 245.76 MHz, and
4. exports an IP catalog package.

After export, add this path as an IP repository in Vivado:

```text
hls_sources/rfdc_iq_derotator/rfdc_iq_derotator_prj/solution1/impl/ip
```

## Practical Notes

This is intentionally not the RFDC internal mixer. It is a fabric-side derotator, so inserting or removing it is visible in the PL datapath and does not silently alter RFDC mixer settings or RFDC-internal latency.

The CORDIC is unrolled for the eight parallel lanes. If HLS reports timing pressure at 245.76 MHz, the first knob to turn is CORDIC/resource pipelining in HLS, not the RFDC settings.
