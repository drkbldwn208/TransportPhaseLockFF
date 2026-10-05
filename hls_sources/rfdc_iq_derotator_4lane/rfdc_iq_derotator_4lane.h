#ifndef RFDC_IQ_DEROTATOR_4LANE_H_
#define RFDC_IQ_DEROTATOR_4LANE_H_

#include <ap_int.h>
#include <hls_stream.h>

/*
 * The RFDC streams in this project are 64 bits wide:
 *
 *   4 lanes/clock * 16 bits/lane = 64 bits
 *
 * Lane packing matches the existing RTL modules:
 *
 *   lane 0 = bits [15:0]
 *   lane 1 = bits [31:16]
 *   ...
 *   lane 3 = bits [63:48]
 *
 * A plain ap_uint<64> AXI-stream payload is used intentionally. HLS will
 * generate TDATA/TVALID/TREADY, without forcing TLAST/TKEEP sideband ports.
 * That makes the output easy to connect to standard Xilinx CIC/FIR Compiler
 * AXI4-Stream inputs.
 *
 * The derotation sine/cosine now use the same 14-bit quarter-wave addressing
 * convention as the existing RTL NCO. The NCO's original table is amplitude
 * scaled for DAC output, so the HLS table is a normalized copy for unit-gain
 * Q1.15 mixer coefficients.
 */
typedef ap_uint<64> axis_iq_bus_t;

static const int RFDC_IQ_DEROTATOR_4LANE_LANES = 4;
static const int RFDC_IQ_DEROTATOR_4LANE_SAMPLE_BITS = 16;

/*
 * At 245.76 MHz and four samples/beat, the sample rate is 983.04 MS/s.
 * Preserve the current eight-lane module's physical rotation frequency:
 * FCW_4 = 2 * 0xF75104D5 modulo 2^32 = 0xFB955555.
 * FCW is the per-sample phase increment; advance by 4 * FCW per beat.
 * The signed frequency is FCW_signed * 983.04e6 / 2^32 (Hz).
 */
// static const ap_uint<32> RFDC_IQ_DEROTATOR_4LANE_ROTATION_FCW = 0xFB955555;
static const ap_uint<32> RFDC_IQ_DEROTATOR_4LANE_ROTATION_FCW = 0x00000000;

/*
 * Top-level HLS function.
 *
 * s_axis_i / s_axis_q:
 *   Separate RFDC I and Q AXI streams, each 4 packed signed 16-bit samples.
 *
 * m_axis_i / m_axis_q:
 *   Separate derotated I and Q AXI streams, with the same 64-bit packing.
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
void rfdc_iq_derotator_4lane(
    hls::stream<axis_iq_bus_t> &s_axis_i,
    hls::stream<axis_iq_bus_t> &s_axis_q,
    hls::stream<axis_iq_bus_t> &m_axis_i,
    hls::stream<axis_iq_bus_t> &m_axis_q,
    bool enable,
    bool reset_phase,
    ap_uint<32> phase_offset);

#endif
