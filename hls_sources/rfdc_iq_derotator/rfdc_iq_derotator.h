#ifndef RFDC_IQ_DEROTATOR_H_
#define RFDC_IQ_DEROTATOR_H_

#include <ap_int.h>
#include <hls_stream.h>

/*
 * The RFDC streams in this project are 128 bits wide:
 *
 *   8 lanes/clock * 16 bits/lane = 128 bits
 *
 * Lane packing matches the existing RTL modules:
 *
 *   lane 0 = bits [15:0]
 *   lane 1 = bits [31:16]
 *   ...
 *   lane 7 = bits [127:112]
 *
 * A plain ap_uint<128> AXI-stream payload is used intentionally. HLS will
 * generate TDATA/TVALID/TREADY, without forcing TLAST/TKEEP sideband ports.
 * That makes the output easy to connect to standard Xilinx CIC/FIR Compiler
 * AXI4-Stream inputs.
 */
typedef ap_uint<128> axis_iq_bus_t;

static const int RFDC_IQ_DEROTATOR_LANES = 8;
static const int RFDC_IQ_DEROTATOR_SAMPLE_BITS = 16;

/*
 * The existing PhaseAccumulator_8Lane reset/default FCW is 0x0B115555, which
 * corresponds to 85 MHz with the 8-lane effective sample rate:
 *
 *   245.76 MHz fabric clock * 8 lanes = 1966.08 MS/s
 *
 * This derotator defaults to twice that frequency, because the monitored
 * signal is frequency-doubled before observation:
 *
 *   2 * 0x0B115555 = 0x1622AAAA
 *
 * The FCW is a per-sample phase increment, not a per-PL-clock increment.
 * Because each bus contains 8 time-interleaved samples, the internal phase
 * accumulator advances by 8 * FCW after each accepted AXI stream beat.
 */
static const ap_uint<32> RFDC_IQ_DEROTATOR_DEFAULT_FCW = 0x0B115555;
static const ap_uint<32> RFDC_IQ_DEROTATOR_ROTATION_FCW = 0x1622AAAA;

/*
 * Top-level HLS function.
 *
 * s_axis_i / s_axis_q:
 *   Separate RFDC I and Q AXI streams, each 8 packed signed 16-bit samples.
 *
 * m_axis_i / m_axis_q:
 *   Separate derotated I and Q AXI streams, with the same 128-bit packing.
 *
 * enable:
 *   1 = apply derotation.
 *   0 = pass I/Q through unchanged. The internal phase still advances for
 *       each accepted beat, so re-enabling preserves sample-time alignment.
 *
 * reset_phase:
 *   Pulse high for one accepted beat to load phase_offset into the internal
 *   derotation phase accumulator. If held high, every beat restarts at the
 *   same phase_offset.
 *
 * phase_offset:
 *   Unsigned 32-bit phase word. 0x00000000 is 0 turns, 0x40000000 is +90 deg,
 *   0x80000000 is 180 deg, and 0xC0000000 is -90 deg.
 */
void rfdc_iq_derotator(
    hls::stream<axis_iq_bus_t> &s_axis_i,
    hls::stream<axis_iq_bus_t> &s_axis_q,
    hls::stream<axis_iq_bus_t> &m_axis_i,
    hls::stream<axis_iq_bus_t> &m_axis_q,
    bool enable,
    bool reset_phase,
    ap_uint<32> phase_offset);

#endif
