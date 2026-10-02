# SSR4 FIR decimator

Decimates four signed 16-bit input samples per beat into one signed 32-bit
output sample, following the existing SSR8-to-one module. Use one instance
for I and another identical instance for Q.

| Quantity | Value |
| --- | --- |
| Fabric clock | 245.76 MHz (4.069 ns constraint) |
| Input rate | 983.04 MS/s |
| Output rate | 245.76 MS/s |
| Input AXI payload | 64 bits: four signed 16-bit samples |
| Output AXI payload | One signed 32-bit sample |
| Output Nyquist | 122.88 MHz |

Input lane 0 occupies bits [15:0] and is earliest; lane 3 occupies bits
[63:48]. The scalar output has no TLAST or TKEEP.

## Filter and startup

The symmetric 255-tap Kaiser-windowed filter uses beta 8.6, a 90 MHz
cutoff, and Q1.17 coefficients. The center tap is corrected for exactly
unity DC gain. The generation expression is in `fir_coeffs.h`; SciPy is
not needed to build the IP.

A dense evaluation of the quantized coefficients gives approximately
-0.0004 to +0.0011 dB gain over 0–60 MHz and at least 78 dB attenuation
from 122.88 MHz through input Nyquist. Integer output rounding adds
signal-dependent error. These frequencies assume the input rate above.

Outputs are causal convolutions ending at input sample n = 4*beat+3,
where beat and n start at zero. The first output follows the 64th
accepted input beat, when the 255-sample history is full (n=255).
Each subsequent input beat produces one output sample.

The FIR group delay is 127 input samples (about 129.19 ns), separate
from the implementation pipeline latency. Accumulators use 56 bits;
outputs round to nearest integer with half ties toward positive infinity
and saturate to signed 32 bits.

`clear` clears history without consuming input or producing output. It
does not flush downstream queues. Blocking stream reads and writes
propagate backpressure. The design requests II=1 with 128 unrolled
coefficient products. Check achieved timing, initiation interval, and
resource use in synthesis before relying on continuous throughput.

## Build and verify

```bash
make csim
make export
make clean
```

`make` defaults to export. Set `VITIS_HLS=/path/to/vitis_hls` if needed.
The target is `xczu49dr-ffvf1760-2-e`.

The testbench checks direct integer convolution for positive/negative DC,
signed extremes, pseudorandom inputs, and impulses on all four lanes,
as well as reset, startup, and output beat count.

After export, add `ssr4_fir_decimator_prj/solution1/impl/ip` from this
directory as a Vivado IP repository. The top function is `ssr4_fir_decimator`.
