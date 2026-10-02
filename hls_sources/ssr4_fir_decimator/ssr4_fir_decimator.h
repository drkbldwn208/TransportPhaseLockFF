#ifndef SSR4_FIR_DECIMATOR_H_
#define SSR4_FIR_DECIMATOR_H_

#include <ap_int.h>
#include <hls_stream.h>

/*
 * Input stream format:
 *
 *   64-bit AXI4-Stream beat = 4 time-interleaved signed 16-bit samples.
 *
 * Lane packing follows the RFDC and existing project convention:
 *
 *   lane 0 = bits [15:0]
 *   lane 1 = bits [31:16]
 *   ...
 *   lane 3 = bits [63:48]
 *
 * Output stream format:
 *
 *   one signed 32-bit sample per AXI4-Stream beat.
 *
 * This module performs a fixed decimation-by-4 FIR. It converts the 4-lane
 * super-sample-rate stream into one scalar stream by producing one filtered
 * output sample for each accepted 4-sample input beat.
 */
typedef ap_uint<64> ssr4_axis_t;
typedef ap_int<32> scalar_axis_t;

static const int SSR4_FIR_LANES = 4;
static const int SSR4_FIR_SAMPLE_BITS = 16;
static const int SSR4_FIR_TAPS = 255;
static const int SSR4_FIR_COEFF_FRAC_BITS = 17;

/*
 * Top-level HLS function.
 *
 * s_axis:
 *   4-lane, 16-bit signed packed input stream.
 *
 * m_axis:
 *   one-lane, 32-bit signed filtered/decimated output stream.
 *
 * clear:
 *   When high, clears the sample history and deasserts input/output transfer.
 *   Hold it high for at least one ap_clk cycle after changing capture modes or
 *   when you want a deterministic filter startup transient.
 */
void ssr4_fir_decimator(
    hls::stream<ssr4_axis_t> &s_axis,
    hls::stream<scalar_axis_t> &m_axis,
    bool clear);

#endif
