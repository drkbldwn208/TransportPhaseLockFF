#ifndef SSR8_FIR_DECIMATOR_H_
#define SSR8_FIR_DECIMATOR_H_

#include <ap_int.h>
#include <hls_stream.h>

/*
 * Input stream format:
 *
 *   128-bit AXI4-Stream beat = 8 time-interleaved signed 16-bit samples.
 *
 * Lane packing follows the RFDC and existing project convention:
 *
 *   lane 0 = bits [15:0]
 *   lane 1 = bits [31:16]
 *   ...
 *   lane 7 = bits [127:112]
 *
 * Output stream format:
 *
 *   one signed 32-bit sample per AXI4-Stream beat.
 *
 * This module performs a fixed decimation-by-8 FIR. It converts the 8-lane
 * super-sample-rate stream into one scalar stream by producing one filtered
 * output sample for each accepted 8-sample input beat.
 */
typedef ap_uint<128> ssr8_axis_t;
typedef ap_int<32> scalar_axis_t;

static const int SSR8_FIR_LANES = 8;
static const int SSR8_FIR_SAMPLE_BITS = 16;
static const int SSR8_FIR_TAPS = 255;
static const int SSR8_FIR_COEFF_FRAC_BITS = 17;

/*
 * Top-level HLS function.
 *
 * s_axis:
 *   8-lane, 16-bit signed packed input stream.
 *
 * m_axis:
 *   one-lane, 32-bit signed filtered/decimated output stream.
 *
 * clear:
 *   When high, clears the sample history and deasserts input/output transfer.
 *   Hold it high for at least one ap_clk cycle after changing capture modes or
 *   when you want a deterministic filter startup transient.
 */
void ssr8_fir_decimator(
    hls::stream<ssr8_axis_t> &s_axis,
    hls::stream<scalar_axis_t> &m_axis,
    bool clear);

#endif
