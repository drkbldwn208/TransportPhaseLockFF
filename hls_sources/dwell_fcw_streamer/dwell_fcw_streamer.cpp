#include "dwell_fcw_streamer.h"

enum streamer_state_t {
    STATE_IDLE = 0,
    STATE_RUN = 1
};

void dwell_fcw_streamer(
    hls::stream<axis_cmd_t> &s_axis_cmd,
    bool start,
    ap_uint<32> *fcw_out,
    ap_uint<1> *active,
    ap_uint<1> *dwell_wait) {
#pragma HLS INTERFACE axis port=s_axis_cmd
#pragma HLS INTERFACE ap_none port=start
#pragma HLS INTERFACE ap_none port=fcw_out
#pragma HLS INTERFACE ap_none port=active
#pragma HLS INTERFACE ap_none port=dwell_wait
#pragma HLS INTERFACE ap_ctrl_none port=return
#pragma HLS PIPELINE II=1

    /*
     * Static variables become hardware registers. Because this function uses
     * ap_ctrl_none, HLS turns it into a free-running block that executes once
     * per ap_clk tick.
     */
    static streamer_state_t state = STATE_IDLE;
    static bool start_d = false;
    static ap_uint<32> current_fcw = DWELL_FCW_STREAMER_IDLE_FCW;
    static ap_uint<32> dwell_remaining = 0;
    static bool current_word_was_last = false;

    /*
     * Drive registered outputs from the state held at the start of this clock.
     * If a stream word is accepted this cycle, current_fcw updates for the next
     * cycle. That one-cycle registered behavior is usually what you want before
     * feeding an NCO or phase accumulator.
     */
    *fcw_out = current_fcw;
    *active = (state == STATE_RUN) ? 1 : 0;
    *dwell_wait = ((state == STATE_RUN) && (dwell_remaining != 0)) ? 1 : 0;

    const bool start_edge = start && !start_d;
    start_d = start;

    if (state == STATE_IDLE) {
        current_fcw = DWELL_FCW_STREAMER_IDLE_FCW;
        dwell_remaining = 0;
        current_word_was_last = false;

        if (start_edge) {
            state = STATE_RUN;
        }

        return;
    }

    /*
     * RUN state.
     *
     * AXI4-Stream TREADY is asserted when HLS reaches s_axis_cmd.read().
     * If TVALID is low at that point, the block waits there with TREADY high
     * and holds its registered outputs. During dwell_remaining != 0, this code
     * does not reach read(), so TREADY stays deasserted and the upstream
     * FIFO/DMA bridge is backpressured.
     */
    if (current_word_was_last && dwell_remaining == 0) {
        state = STATE_IDLE;
        current_fcw = DWELL_FCW_STREAMER_IDLE_FCW;
        current_word_was_last = false;
    } else if (dwell_remaining != 0) {
        dwell_remaining--;

        if (current_word_was_last && dwell_remaining == 0) {
            state = STATE_IDLE;
            current_fcw = DWELL_FCW_STREAMER_IDLE_FCW;
            current_word_was_last = false;
        }
    } else {
        axis_cmd_t command_word = s_axis_cmd.read();
        ap_uint<64> payload = command_word.data;

        current_fcw = payload.range(63, 32);
        dwell_remaining = payload.range(31, 0);
        current_word_was_last = (command_word.last != 0);
    }
}
