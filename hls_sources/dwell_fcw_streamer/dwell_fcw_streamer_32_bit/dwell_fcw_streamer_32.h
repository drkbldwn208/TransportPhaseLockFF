#ifndef DWELL_FCW_STREAMER_32_H_
#define DWELL_FCW_STREAMER_32_H_

#include <ap_axi_sdata.h>
#include <ap_int.h>
#include <hls_stream.h>

/*
 * One command arrives as one 32-bit AXI4-Stream transfer:
 *
 *   bits [31:16] = 16-bit frequency control word, FCW
 *   bits [15: 0] = 16-bit dwell_cycles
 *
 * The AXI4-Stream TLAST sideband is used as an optional packet end marker.
 * When a TLAST command finishes its dwell time, the module returns to IDLE.
 *
 * The 16-bit dwell field is used full-scale. A command with dwell_cycles =
 * 0xffff holds the FCW for about 65536 ap_clk cycles before the next command
 * is accepted. At 245.76 MHz, that is about 267 us.
 */
typedef ap_axiu<32, 0, 0, 0> axis_cmd32_t;

/*
 * This project currently uses an 8-lane phase accumulator. With a 245.76 MHz
 * PL clock, that accumulator advances eight samples per PL clock, so the NCO
 * sample rate is:
 *
 *   245.76 MHz * 8 = 1966.08 MHz
 *
 * FCW = round(output_frequency / sample_rate * 2^32)
 *
 * For an 85 MHz tone in that 8-lane datapath:
 *
 *   round(85e6 / 1966.08e6 * 2^32) = 0x0B115555
 *
 * If this HLS IP is later connected to a single-sample-per-clock phase
 * accumulator running directly at 245.76 MHz, use 0x588AAAAB instead.
 */
static const ap_uint<32> FCW_85MHZ_8LANE_245P76MHZ = 0x0B115555;
static const ap_uint<32> FCW_85MHZ_SINGLE_LANE_245P76MHZ = 0x588AAAAB;
static const ap_uint<16> FCW_85MHZ_16BIT_8LANE_245P76MHZ = 0x0B11;
static const ap_uint<16> FCW_85MHZ_16BIT_SINGLE_LANE_245P76MHZ = 0x588B;

#ifndef DWELL_FCW_STREAMER_IDLE_FCW
#define DWELL_FCW_STREAMER_IDLE_FCW 0x0
#endif

/*
 * Top-level HLS function.
 *
 * Ports after synthesis:
 *   s_axis_cmd      AXI4-Stream slave input carrying packed 32-bit commands.
 *   start           Level input. A rising edge starts the command player.
 *   fcw_out         Current 16-bit frequency control word.
 *   active          1 while the player is in the RUN state.
 *   dwell_wait      1 while the player is holding the current FCW and counting
 *                   down before allowing the next stream read.
 *
 * start must already be synchronous to ap_clk. If it comes from another clock
 * domain, synchronize it before connecting it to this IP.
 */
void dwell_fcw_streamer_32(
    hls::stream<axis_cmd32_t> &s_axis_cmd,
    bool start,
    ap_uint<16> *fcw_out,
    ap_uint<1> *active,
    ap_uint<1> *dwell_wait);

#endif
