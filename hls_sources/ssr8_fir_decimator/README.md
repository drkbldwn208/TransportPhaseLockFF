# SSR8 FIR Decimator HLS IP

This HLS IP converts one 8-lane super-sample-rate stream into one scalar stream using a fixed decimation-by-8 FIR.

Use one instance for `I` and one identical instance for `Q`.

```text
128-bit SSR input:  8 lanes * signed 16-bit samples
32-bit output:      1 signed sample per beat
decimation:         8 input samples -> 1 output sample
```

## Should This Be Xilinx FIR Compiler?

If you want the most production-ready block, the Xilinx FIR Compiler is still the default recommendation. It already knows how to build parallel/SSR FIRs, decimators, symmetric coefficient optimizations, rounding, reloadable coefficients, and timing-friendly pipelines.

A custom HLS module is reasonable here if:

- the filter coefficients are fixed or rarely changed,
- you want to understand and control the exact lane packing,
- you are happy to trade DSPs/registers for a simple always-one-output-per-clock architecture,
- you do not need all the configurability of FIR Compiler.

The important distinction is latency versus throughput. Added latency is fine for phase-noise traces, but the module still has to sustain the RFDC fabric stream. At 245.76 MHz fabric clock with eight samples per beat, a decimate-by-8 FIR produces one scalar output every clock. A slow multi-cycle MAC would need input buffering and would eventually backpressure or drop a continuous RFDC stream.

## Tap Recommendation

For this first SSR8-to-one-lane decimator, start with **255 taps**.

That is a good practical default because:

- it is long enough to give a clean anti-alias transition before the new 122.88 MHz Nyquist frequency,
- symmetry reduces the multiply count to 128 DSP multiplies per instance,
- the ZCU216-class RFSoC has enough DSP budget for one `I` and one `Q` instance in many designs,
- the latency is not important for your long phase-noise captures.

Useful starting points:

```text
127 taps: okay if you only care about a narrow baseband, roughly <= 25-30 MHz, and moderate stopband rejection.
255 taps: recommended default for a cleaner first decimate-by-8 stage, roughly <= 60 MHz useful baseband.
511 taps: use only if you need a very wide passband near the decimated Nyquist or very high stopband rejection in one stage.
```

For several-second phase-noise traces, a multi-stage chain is usually better than trying to do everything in one FIR:

```text
RFDC/derotated SSR8 stream
  -> 255-tap FIR decimate-by-8, 1966.08 MS/s to 245.76 MS/s
  -> CIC or halfband/FIR stages at lower rates
  -> DMA capture
```

## Default Coefficients

The included coefficient set is a 255-tap symmetric Kaiser-windowed low-pass FIR:

```text
input sample rate:       1966.08 MS/s
decimation factor:       8
output sample rate:      245.76 MS/s
planning passband edge:  about 60 MHz
first alias edge:        122.88 MHz
coefficient format:      signed Q1.17
DC gain:                 exactly 1.0 after quantization
```

The coefficients are intentionally conservative for a first custom block. Once you know the bandwidth you actually need for phase-noise analysis, redesign the coefficients around that bandwidth.

## Data Format

Input lane packing:

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

The module stores the newest received sample at the front of the FIR history. After one input beat arrives, sample 7 is the newest sample and sample 0 is seven samples older.

## Ports

Top function:

```cpp
void ssr8_fir_decimator(
    hls::stream<ssr8_axis_t> &s_axis,
    hls::stream<scalar_axis_t> &m_axis,
    bool clear);
```

After HLS synthesis:

- `s_axis`: 128-bit AXI4-Stream input.
- `m_axis`: 32-bit AXI4-Stream output.
- `clear`: simple input that clears filter history and suppresses transfers while high.

The output is 32-bit signed to preserve FIR accumulator precision for later processing or DMA packing. If you need 16-bit output for a specific downstream IP, add a saturation/truncation shim or change `scalar_axis_t` to `ap_int<16>`.

## Startup Behavior

The FIR history starts at zero. The module waits until the 255-tap history has been filled before producing output samples.

With eight input samples per beat:

```text
ceil(255 / 8) = 32 input beats
```

So the first valid output appears after 32 accepted input beats.

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
hls_sources/ssr8_fir_decimator/ssr8_fir_decimator_prj/solution1/impl/ip
```

## Plotting C-Sim Results

The C testbench writes two CSV files for plotting:

```text
csim_frequency_response.csv
csim_filter_results.csv
```

`csim_frequency_response.csv` is the main characterization file. It contains a swept C-sim measurement from DC through the input Nyquist band:

```text
freq_hz,normalized_input_freq,input_amplitude,output_amplitude,gain_db,valid_samples
```

The scan measures true DC, then 512 half-bin-spaced frequencies across `0` to `983.04 MHz`. Half-bin spacing avoids exact aliases at multiples of the output sample rate, where a real-only sine scan can become phase-dependent after decimation.

`csim_filter_results.csv` is a small time-domain smoke test. It contains:

```text
beat,input_newest,output_valid,output_sample
```

The time-domain smoke-test stimulus is a two-tone signal:

```text
10 MHz tone:   intended passband tone
180 MHz tone:  intended stopband/alias-rejection tone
```

After running C simulation, generate a PNG:

```bash
python3 plot_csim_filter_results.py
```

The script searches both the current directory and the usual HLS C-sim build folder:

```text
ssr8_fir_decimator_prj/solution1/csim/build/csim_frequency_response.csv
ssr8_fir_decimator_prj/solution1/csim/build/csim_filter_results.csv
```

The output plot defaults to:

```text
csim_frequency_response.png
```

Useful options:

```bash
python3 plot_csim_filter_results.py --response-csv path/to/csim_frequency_response.csv
python3 plot_csim_filter_results.py --time-csv path/to/csim_filter_results.csv
python3 plot_csim_filter_results.py --out my_filter_plot.png
python3 plot_csim_filter_results.py --passband-mhz 40
```

The first subplot shows the measured full-band response. The second subplot zooms into the passband. If the time-domain smoke-test CSV is present, the script also adds a third subplot showing the newest input lane and decimated output.
