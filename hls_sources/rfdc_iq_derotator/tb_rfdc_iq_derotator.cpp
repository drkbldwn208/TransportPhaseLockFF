#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>

#include "rfdc_iq_derotator.h"

static void pack_lane(axis_iq_bus_t &word, int lane, ap_int<16> sample) {
    word.range(lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS + 15,
               lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS) = (ap_uint<16>)sample;
}

static ap_int<16> unpack_lane(axis_iq_bus_t word, int lane) {
    ap_uint<16> bits =
        word.range(lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS + 15,
                   lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS);
    return (ap_int<16>)bits;
}

static axis_iq_bus_t make_bus(bool make_i, int bus_index, double amplitude) {
    axis_iq_bus_t word = 0;
    const double two_pi = 6.28318530717958647692;
    const double turns_per_sample =
        (double)RFDC_IQ_DEROTATOR_ROTATION_FCW.to_uint() / 4294967296.0;

    for (int lane = 0; lane < RFDC_IQ_DEROTATOR_LANES; lane++) {
        int sample_index = bus_index * RFDC_IQ_DEROTATOR_LANES + lane;
        double phase = two_pi * turns_per_sample * sample_index;
        double value = make_i ? amplitude * std::cos(phase)
                              : amplitude * std::sin(phase);
        pack_lane(word, lane, (ap_int<16>)std::lround(value));
    }

    return word;
}

int main() {
    hls::stream<axis_iq_bus_t> s_i("s_i");
    hls::stream<axis_iq_bus_t> s_q("s_q");
    hls::stream<axis_iq_bus_t> m_i("m_i");
    hls::stream<axis_iq_bus_t> m_q("m_q");

    const double amplitude = 12000.0;
    const int buses_to_test = 32;
    const int tolerance_lsb = 48;
    int errors = 0;

    for (int bus = 0; bus < buses_to_test; bus++) {
        s_i.write(make_bus(true, bus, amplitude));
        s_q.write(make_bus(false, bus, amplitude));

        bool reset_phase = (bus == 0);
        rfdc_iq_derotator(s_i, s_q, m_i, m_q, true, reset_phase, 0);

        axis_iq_bus_t i_out = m_i.read();
        axis_iq_bus_t q_out = m_q.read();

        for (int lane = 0; lane < RFDC_IQ_DEROTATOR_LANES; lane++) {
            int i_sample = unpack_lane(i_out, lane).to_int();
            int q_sample = unpack_lane(q_out, lane).to_int();
            int i_error = std::abs(i_sample - (int)amplitude);
            int q_error = std::abs(q_sample);

            if (i_error > tolerance_lsb || q_error > tolerance_lsb) {
                std::cerr << "FAIL bus=" << bus << " lane=" << lane
                          << " I=" << i_sample << " Q=" << q_sample
                          << " Ierr=" << i_error << " Qerr=" << q_error << "\n";
                errors++;
            }
        }
    }

    /*
     * Verify pass-through mode on one arbitrary bus. The phase accumulator still
     * advances internally, but enable=0 should leave payload samples unchanged.
     */
    axis_iq_bus_t pass_i = make_bus(true, 3, amplitude);
    axis_iq_bus_t pass_q = make_bus(false, 3, amplitude);
    s_i.write(pass_i);
    s_q.write(pass_q);
    rfdc_iq_derotator(s_i, s_q, m_i, m_q, false, false, 0);

    axis_iq_bus_t pass_i_out = m_i.read();
    axis_iq_bus_t pass_q_out = m_q.read();
    if (pass_i_out != pass_i || pass_q_out != pass_q) {
        std::cerr << "FAIL pass-through mode changed samples\n";
        errors++;
    }

    if (errors == 0) {
        std::cout << "PASS\n";
    }

    return errors;
}
