#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>

#include "rfdc_iq_derotator_4lane.h"

static void pack_lane(axis_iq_bus_t &word, int lane, ap_int<16> sample) {
    word.range(lane * RFDC_IQ_DEROTATOR_4LANE_SAMPLE_BITS + 15,
               lane * RFDC_IQ_DEROTATOR_4LANE_SAMPLE_BITS) = (ap_uint<16>)sample;
}

static ap_int<16> unpack_lane(axis_iq_bus_t word, int lane) {
    ap_uint<16> bits =
        word.range(lane * RFDC_IQ_DEROTATOR_4LANE_SAMPLE_BITS + 15,
                   lane * RFDC_IQ_DEROTATOR_4LANE_SAMPLE_BITS);
    return (ap_int<16>)bits;
}

static axis_iq_bus_t make_bus(bool make_i, int bus_index, double amplitude) {
    axis_iq_bus_t word = 0;
    const double two_pi = 6.28318530717958647692;
    const double turns_per_sample =
        (double)RFDC_IQ_DEROTATOR_4LANE_ROTATION_FCW.to_uint() / 4294967296.0;

    for (int lane = 0; lane < RFDC_IQ_DEROTATOR_4LANE_LANES; lane++) {
        int sample_index = bus_index * RFDC_IQ_DEROTATOR_4LANE_LANES + lane;
        double phase = two_pi * turns_per_sample * sample_index;
        // Drive A*exp(+j*phase) to cancel the exp(-j*phase) mixer.
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
        rfdc_iq_derotator_4lane(s_i, s_q, m_i, m_q, true, reset_phase, 0);

        axis_iq_bus_t i_out = m_i.read();
        axis_iq_bus_t q_out = m_q.read();

        for (int lane = 0; lane < RFDC_IQ_DEROTATOR_4LANE_LANES; lane++) {
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
    rfdc_iq_derotator_4lane(s_i, s_q, m_i, m_q, false, false, 0);

    axis_iq_bus_t pass_i_out = m_i.read();
    axis_iq_bus_t pass_q_out = m_q.read();
    if (pass_i_out != pass_i || pass_q_out != pass_q) {
        std::cerr << "FAIL pass-through mode changed samples\n";
        errors++;
    }

    // Check arbitrary I/Q, phase offsets, wraparound, repeated reset,
    // clipping, and phase continuity across bypassed beats.
    uint32_t phase = 0;
    const uint32_t fcw = RFDC_IQ_DEROTATOR_4LANE_ROTATION_FCW.to_uint();
    for (int bus = 0; bus < 80; bus++) {
        const bool reset = bus == 0 || bus == 20 || bus == 21;
        const bool enable = !(bus >= 8 && bus < 12);
        const uint32_t offset = bus == 0 ? 0xF0000000U : 0x40000000U;
        if (reset) phase = offset;
        axis_iq_bus_t i_word = 0;
        axis_iq_bus_t q_word = 0;
        for (int lane = 0; lane < RFDC_IQ_DEROTATOR_4LANE_LANES; lane++) {
            pack_lane(i_word, lane, lane % 2 ? -32768 : 32767);
            pack_lane(q_word, lane, lane < 2 ? 32767 : -20000);
        }
        s_i.write(i_word);
        s_q.write(q_word);
        rfdc_iq_derotator_4lane(s_i, s_q, m_i, m_q, enable, reset, offset);
        axis_iq_bus_t actual_i = m_i.read();
        axis_iq_bus_t actual_q = m_q.read();
        for (int lane = 0; lane < RFDC_IQ_DEROTATOR_4LANE_LANES; lane++) {
            const uint32_t lane_phase = phase + fcw * lane;
            const double angle = 6.28318530717958647692 * lane_phase / 4294967296.0;
            const int i = unpack_lane(i_word, lane).to_int();
            const int q = unpack_lane(q_word, lane).to_int();
            long expected_i = enable ? std::lround(i * std::cos(angle) + q * std::sin(angle)) : i;
            long expected_q = enable ? std::lround(q * std::cos(angle) - i * std::sin(angle)) : q;
            if (expected_i > 32767) expected_i = 32767;
            if (expected_i < -32768) expected_i = -32768;
            if (expected_q > 32767) expected_q = 32767;
            if (expected_q < -32768) expected_q = -32768;
            const int tolerance = enable ? tolerance_lsb : 0;
            if (std::abs(unpack_lane(actual_i, lane).to_int() - expected_i) > tolerance ||
                std::abs(unpack_lane(actual_q, lane).to_int() - expected_q) > tolerance) {
                std::cerr << "FAIL phase/control test bus=" << bus << " lane=" << lane << "\n";
                errors++;
            }
        }
        phase += RFDC_IQ_DEROTATOR_4LANE_LANES * fcw;
        if (!s_i.empty() || !s_q.empty() || !m_i.empty() || !m_q.empty()) errors++;
    }

    if (errors == 0) {
        std::cout << "PASS\n";
    }

    return errors;
}
