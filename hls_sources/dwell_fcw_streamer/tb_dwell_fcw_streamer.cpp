#include <iomanip>
#include <iostream>

#include "dwell_fcw_streamer.h"

static axis_cmd_t make_command(ap_uint<32> fcw, ap_uint<32> dwell_cycles, bool last) {
    axis_cmd_t word;
    word.data.range(63, 32) = fcw;
    word.data.range(31, 0) = dwell_cycles;
    word.keep = 0xFF;
    word.strb = 0xFF;
    word.last = last ? 1 : 0;
    return word;
}

static int check_equal_u32(const char *name, ap_uint<32> got, ap_uint<32> expected) {
    if (got != expected) {
        std::cerr << "FAIL: " << name << " got 0x" << std::hex << got.to_uint()
                  << " expected 0x" << expected.to_uint() << std::dec << "\n";
        return 1;
    }
    return 0;
}

static void tick(
    hls::stream<axis_cmd_t> &commands,
    bool start,
    ap_uint<32> &fcw_out,
    ap_uint<1> &active,
    ap_uint<1> &dwell_wait,
    int cycle) {
    dwell_fcw_streamer(commands, start, &fcw_out, &active, &dwell_wait);

    std::cout << "cycle " << std::setw(2) << cycle
              << " start=" << start
              << " fcw=0x" << std::hex << std::setw(8) << std::setfill('0')
              << fcw_out.to_uint() << std::dec << std::setfill(' ')
              << " active=" << active
              << " dwell_wait=" << dwell_wait << "\n";
}

int main() {
    hls::stream<axis_cmd_t> commands("commands");

    const ap_uint<32> idle_fcw = FCW_85MHZ_8LANE_245P76MHZ;
    const ap_uint<32> fcw_a = 0x11112222;
    const ap_uint<32> fcw_b = 0x33334444;

    ap_uint<32> fcw_out = 0;
    ap_uint<1> active = 0;
    ap_uint<1> dwell_wait = 0;
    int errors = 0;
    int cycle = 0;

    /*
     * While idle, the output should be the default 85 MHz FCW and the stream
     * should not be consumed.
     */
    tick(commands, false, fcw_out, active, dwell_wait, cycle++);
    errors += check_equal_u32("idle FCW", fcw_out, idle_fcw);
    if (active != 0) {
        std::cerr << "FAIL: active should be 0 while idle\n";
        errors++;
    }

    commands.write(make_command(fcw_a, 3, false));
    commands.write(make_command(fcw_b, 2, true));

    /*
     * A rising edge starts the player. The first command is accepted on the
     * following RUN cycle, then the block waits three cycles before accepting
     * the second command.
     */
    tick(commands, true, fcw_out, active, dwell_wait, cycle++);
    tick(commands, false, fcw_out, active, dwell_wait, cycle++);
    tick(commands, false, fcw_out, active, dwell_wait, cycle++);
    errors += check_equal_u32("first command FCW", fcw_out, fcw_a);

    tick(commands, false, fcw_out, active, dwell_wait, cycle++);
    tick(commands, false, fcw_out, active, dwell_wait, cycle++);
    tick(commands, false, fcw_out, active, dwell_wait, cycle++);

    /*
     * The second command has TLAST. After its dwell time completes, the module
     * returns to IDLE and the default 85 MHz word appears again.
     */
    tick(commands, false, fcw_out, active, dwell_wait, cycle++);
    errors += check_equal_u32("second command FCW", fcw_out, fcw_b);

    tick(commands, false, fcw_out, active, dwell_wait, cycle++);
    tick(commands, false, fcw_out, active, dwell_wait, cycle++);
    tick(commands, false, fcw_out, active, dwell_wait, cycle++);
    errors += check_equal_u32("return-to-idle FCW", fcw_out, idle_fcw);

    if (errors == 0) {
        std::cout << "PASS\n";
    }

    return errors;
}
