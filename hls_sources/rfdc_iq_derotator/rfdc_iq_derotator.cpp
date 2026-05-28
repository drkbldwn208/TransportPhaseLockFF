#include "rfdc_iq_derotator.h"
#include "rfdc_iq_derotator_lut.h"

typedef ap_int<16> sample_t;
typedef ap_int<16> coeff_t;
typedef ap_int<48> mix_acc_t;

static const int NCO_LUT_ADDR_BITS = 14;
static const int NCO_LUT_SIZE = 1 << NCO_LUT_ADDR_BITS;

static sample_t round_saturate_to_i16(mix_acc_t value) {
#pragma HLS INLINE
    const mix_acc_t round = 1 << 14;
    mix_acc_t shifted = (value + round) >> 15;

    if (shifted > 32767) {
        return 32767;
    }
    if (shifted < -32768) {
        return -32768;
    }

    return (sample_t)shifted;
}

static coeff_t nco_sine_q15(ap_uint<32> phase) {
#pragma HLS INLINE
    ap_uint<2> quadrant = phase.range(31, 30);
    ap_uint<NCO_LUT_ADDR_BITS> addr = phase.range(29, 16);
    ap_uint<NCO_LUT_ADDR_BITS> lut_addr =
        quadrant[0] ? (ap_uint<NCO_LUT_ADDR_BITS>)(NCO_LUT_SIZE - 1 - addr)
                    : addr;

    ap_int<17> magnitude = RFDC_IQ_DEROTATOR_SINE_LUT[lut_addr];
    ap_int<17> signed_value = quadrant[1] ? (ap_int<17>)-magnitude : magnitude;
    return (coeff_t)signed_value;
}

static void sincos_q15(ap_uint<32> phase, coeff_t *cos_out, coeff_t *sin_out) {
#pragma HLS INLINE
    *sin_out = nco_sine_q15(phase);
    *cos_out = nco_sine_q15(phase + (ap_uint<32>)0x40000000);
}

static void rotate_one_sample(
    sample_t i_in,
    sample_t q_in,
    ap_uint<32> phase,
    bool enable,
    sample_t *i_out,
    sample_t *q_out) {
#pragma HLS INLINE
    if (!enable) {
        *i_out = i_in;
        *q_out = q_in;
        return;
    }

    coeff_t cos_phase;
    coeff_t sin_phase;
    sincos_q15(phase, &cos_phase, &sin_phase);

    /*
     * This sign convention multiplies by exp(+j*phase):
     *
     *   (I + jQ) * (cos(phase) + j sin(phase))
     *
     * so a measured negative phase ramp, I + jQ ~= A*exp(-j*phase),
     * is brought to baseband as approximately A + j0.
     */
    mix_acc_t i_mix = (mix_acc_t)i_in * cos_phase + (mix_acc_t)q_in * sin_phase;
    mix_acc_t q_mix = (mix_acc_t)q_in * cos_phase - (mix_acc_t)i_in * sin_phase;

    *i_out = round_saturate_to_i16(i_mix);
    *q_out = round_saturate_to_i16(q_mix);
}

void rfdc_iq_derotator(
    hls::stream<axis_iq_bus_t> &s_axis_i,
    hls::stream<axis_iq_bus_t> &s_axis_q,
    hls::stream<axis_iq_bus_t> &m_axis_i,
    hls::stream<axis_iq_bus_t> &m_axis_q,
    bool enable,
    bool reset_phase,
    ap_uint<32> phase_offset) {
#pragma HLS INTERFACE axis port=s_axis_i
#pragma HLS INTERFACE axis port=s_axis_q
#pragma HLS INTERFACE axis port=m_axis_i
#pragma HLS INTERFACE axis port=m_axis_q
#pragma HLS INTERFACE ap_none port=enable
#pragma HLS INTERFACE ap_none port=reset_phase
#pragma HLS INTERFACE ap_none port=phase_offset
#pragma HLS INTERFACE ap_ctrl_none port=return
#pragma HLS PIPELINE II=1

    static ap_uint<32> phase_acc = 0;

    axis_iq_bus_t i_word = s_axis_i.read();
    axis_iq_bus_t q_word = s_axis_q.read();
    axis_iq_bus_t i_rot_word = 0;
    axis_iq_bus_t q_rot_word = 0;

    ap_uint<32> bus_start_phase = reset_phase ? phase_offset : phase_acc;

ROTATE_LANES:
    for (int lane = 0; lane < RFDC_IQ_DEROTATOR_LANES; lane++) {
#pragma HLS UNROLL
        ap_uint<16> i_bits =
            i_word.range(lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS + 15,
                         lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS);
        ap_uint<16> q_bits =
            q_word.range(lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS + 15,
                         lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS);

        sample_t i_sample = (sample_t)i_bits;
        sample_t q_sample = (sample_t)q_bits;
        sample_t i_rot;
        sample_t q_rot;

        ap_uint<32> lane_phase =
            bus_start_phase + (ap_uint<32>)(RFDC_IQ_DEROTATOR_ROTATION_FCW * lane);

        rotate_one_sample(i_sample, q_sample, lane_phase, enable, &i_rot, &q_rot);

        i_rot_word.range(lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS + 15,
                         lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS) =
            (ap_uint<16>)i_rot;
        q_rot_word.range(lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS + 15,
                         lane * RFDC_IQ_DEROTATOR_SAMPLE_BITS) =
            (ap_uint<16>)q_rot;
    }

    phase_acc =
        bus_start_phase + (ap_uint<32>)(RFDC_IQ_DEROTATOR_ROTATION_FCW *
                                        RFDC_IQ_DEROTATOR_LANES);

    m_axis_i.write(i_rot_word);
    m_axis_q.write(q_rot_word);
}
