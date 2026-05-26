# Dwell FCW Streamer HLS IP

This folder contains a small Vitis/Vivado HLS module for feeding a frequency control word (FCW) into the existing NCO/phase-accumulator path.

The module is a two-state machine:

1. `IDLE`: output the default FCW for an 85 MHz tone and do not read AXI stream data.
2. `RUN`: after a rising edge on `start`, read commands from an AXI4-Stream FIFO. Each command updates `fcw_out`, then the module waits `dwell_cycles` PL clocks before accepting the next command.

## Files

- `dwell_fcw_streamer.h`: top function declaration, AXI stream word type, and FCW constants.
- `dwell_fcw_streamer.cpp`: synthesizable HLS implementation.
- `tb_dwell_fcw_streamer.cpp`: simple C simulation testbench.
- `run_hls.tcl`: Vitis/Vivado HLS script for C simulation, synthesis, and IP export.

## Command Format

Each AXI4-Stream transfer is one 64-bit command:

```text
63                              32 31                               0
+---------------------------------+----------------------------------+
| frequency control word, FCW     | dwell_cycles                    |
+---------------------------------+----------------------------------+
```

Software-side packing:

```c
uint64_t command = ((uint64_t)fcw << 32) | dwell_cycles;
```

`TLAST` is treated as the end of a command packet. After the `TLAST` command finishes its dwell time, the module returns to `IDLE` and outputs the default 85 MHz FCW again. If you want the streamer to stay in `RUN` forever, keep `TLAST` low.

## Ports

The HLS top function is:

```cpp
void dwell_fcw_streamer(
    hls::stream<axis_cmd_t> &s_axis_cmd,
    bool start,
    ap_uint<32> *fcw_out,
    ap_uint<1> *active,
    ap_uint<1> *dwell_wait);
```

After HLS synthesis:

- `s_axis_cmd` becomes an AXI4-Stream slave input.
- `start` is a simple one-bit input. A rising edge starts the player.
- `fcw_out` is the current 32-bit frequency control word.
- `active` is high in the `RUN` state.
- `dwell_wait` is high while the module is counting down before the next stream read.

The `start` input must be synchronous to the HLS `ap_clk`. If the edge comes from another clock domain, synchronize it before this IP.

## Why TREADY Deasserts During Dwell

In HLS, an AXI4-Stream input is consumed when the code calls:

```cpp
axis_cmd_t command_word = s_axis_cmd.read();
```

The generated hardware asserts `TREADY` when the module is ready to execute that read. This design reaches `read()` only when:

- the state machine is in `RUN`,
- `dwell_remaining == 0`.

If the FIFO is empty at that moment, the hardware waits with `TREADY` asserted until `TVALID` arrives. While `dwell_remaining != 0`, the code does not read the stream, so the generated AXI stream interface backpressures the upstream FIFO by leaving `TREADY` deasserted.

## HLS Concepts Used Here

The source is written like C++, but each call of the top function represents one hardware clock tick after synthesis.

```cpp
#pragma HLS INTERFACE ap_ctrl_none port=return
```

`ap_ctrl_none` tells HLS to make a free-running hardware block. There is no AXI-Lite start/done control register. Once reset is released, the logic runs every `ap_clk`.

```cpp
static ap_uint<32> current_fcw;
```

A `static` variable inside the top function becomes a hardware register. That is how the module remembers the current state, previous `start` value, current FCW, and remaining dwell count from one clock to the next.

```cpp
#pragma HLS PIPELINE II=1
```

This asks HLS to schedule the function so the state machine can advance once per clock. The design does very little work per cycle, so the intended initiation interval is one PL clock.

## Dwell Timing

`dwell_cycles` is counted in HLS `ap_clk` cycles. With your 245.76 MHz PL clock:

```text
one PL clock = 1 / 245.76 MHz = 4.069 ns
dwell time  = dwell_cycles * 4.069 ns
```

Examples:

```text
dwell_cycles = 245760      -> 1.000 ms
dwell_cycles = 24576       -> 100.0 us
dwell_cycles = 246         -> about 1.001 us
```

The FCW output is registered. Practically, this means a newly accepted stream command appears on `fcw_out` on the following PL clock. That is normal for a hardware module feeding an NCO or phase accumulator.

For example, if command A has `dwell_cycles = 3`, the module accepts A, presents A on `fcw_out`, holds off the next stream read for three PL clocks, then accepts command B when the dwell counter reaches zero.

## 85 MHz Default FCW

This project has an 8-lane phase accumulator. The PL fabric clock is 245.76 MHz, but the accumulator advances eight output samples per PL clock:

```text
effective NCO sample rate = 245.76 MHz * 8 = 1966.08 MHz
```

The FCW formula is:

```text
FCW = round(output_frequency / sample_rate * 2^32)
```

For an 85 MHz tone in the existing 8-lane datapath:

```text
FCW = round(85e6 / 1966.08e6 * 2^32)
    = 185685333 decimal
    = 0x0B115555
```

That value matches the reset default already present in `PhaseAccumulator_8Lane.sv`.

If you later connect this IP to a single-sample-per-clock accumulator running at 245.76 MHz, the 85 MHz word would instead be:

```text
FCW = round(85e6 / 245.76e6 * 2^32)
    = 1485482667 decimal
    = 0x588AAAAB
```

To override the default without editing the source, define `DWELL_FCW_STREAMER_IDLE_FCW` before compilation.

## Running HLS

From this directory:

```bash
vitis_hls -f run_hls.tcl
```

The script:

1. creates an HLS project,
2. runs C simulation,
3. synthesizes for `xczu49dr-ffvf1760-2-e`, and
4. exports an IP catalog package.

The clock constraint is 4.069 ns, matching 245.76 MHz.

## Block Design Notes

A typical connection is:

```text
PS DMA -> AXI4-Stream Clock Converter/Data FIFO -> dwell_fcw_streamer -> PhaseAccumulator center_freq_word
```

Use an AXI4-Stream FIFO or clock converter between PS/DMA and this IP when the DMA side and PL NCO side are in different clock domains. This HLS module should live entirely in the 245.76 MHz PL clock domain.

The exported IP will also have HLS-generated `ap_clk` and reset ports. Connect `ap_clk` to the same PL clock used by the NCO/phase accumulator.

After export, add this folder to Vivado as an IP repository:

```text
hls_sources/dwell_fcw_streamer/dwell_fcw_streamer_prj/solution1/impl/ip
```

Then instantiate the IP in the block design, connect `s_axis_cmd` to the AXI stream FIFO output, and connect `fcw_out` to the phase accumulator `center_freq_word` input.
