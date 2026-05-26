#include "rfdc_iq_derotator.h"

typedef ap_int<16> sample_t;
typedef ap_int<16> coeff_t;
typedef ap_int<32> cordic_data_t;
typedef ap_int<48> mix_acc_t;

static const int CORDIC_ITERATIONS = 20;
static const cordic_data_t CORDIC_K_Q30 = 0x26DD3B6A;

/*
 * atan(2^-i), represented as unsigned phase turns:
 *
 *   2^32 counts = one full turn = 2*pi radians
 *
 * The first value is atan(1) = 45 degrees = 0x20000000 turns.
 */
static const cordic_data_t CORDIC_ATAN_TABLE[CORDIC_ITERATIONS] = {
    0x20000000, 0x12E4051E, 0x09FB385B, 0x051111D4,
    0x028B0D43, 0x0145D7E1, 0x00A2F61E, 0x00517C55,
    0x0028BE53, 0x00145F2F, 0x000A2F98, 0x000517CC,
    0x00028BE6, 0x000145F3, 0x0000A2FA, 0x0000517D,
    0x000028BE, 0x0000145F, 0x00000A30, 0x00000518
};

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

static coeff_t q30_to_q15(cordic_data_t value) {
#pragma HLS INLINE
    ap_int<34> rounded = value;
    rounded += 1 << 14;
    ap_int<34> shifted = rounded >> 15;

    if (shifted > 32767) {
        return 32767;
    }
    if (shifted < -32768) {
        return -32768;
    }

    return (coeff_t)shifted;
}

static void sincos_q15(ap_uint<32> phase, coeff_t *cos_out, coeff_t *sin_out) {
#pragma HLS INLINE
#pragma HLS ARRAY_PARTITION variable=CORDIC_ATAN_TABLE complete dim=1
    const ap_int<33> full_turn = ((ap_int<33>)1) << 32;
    const ap_int<33> pi = ((ap_int<33>)1) << 31;
    const ap_int<33> half_pi = ((ap_int<33>)1) << 30;

    /*
     * Convert the unsigned phase word into a signed angle in [-pi, pi), then
     * fold it into the CORDIC convergence range [-pi/2, pi/2]. If we subtract
     * or add pi during folding, both sine and cosine change sign.
     */
    ap_int<33> z = phase;
    if (phase[31]) {
        z -= full_turn;
    }

    bool negate_result = false;
    if (z > half_pi) {
        z -= pi;
        negate_result = true;
    } else if (z < -half_pi) {
        z += pi;
        negate_result = true;
    }

    cordic_data_t x = CORDIC_K_Q30;
    cordic_data_t y = 0;

CORDIC_ROTATE:
    for (int i = 0; i < CORDIC_ITERATIONS; i++) {
#pragma HLS UNROLL
        cordic_data_t x_old = x;
        cordic_data_t y_old = y;

        if (z >= 0) {
            x = x_old - (y_old >> i);
            y = y_old + (x_old >> i);
            z -= CORDIC_ATAN_TABLE[i];
        } else {
            x = x_old + (y_old >> i);
            y = y_old - (x_old >> i);
            z += CORDIC_ATAN_TABLE[i];
        }
    }

    if (negate_result) {
        x = -x;
        y = -y;
    }

    *cos_out = q30_to_q15(x);
    *sin_out = q30_to_q15(y);
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
     * Derotation means multiplying by exp(-j*phase):
     *
     *   (I + jQ) * (cos(phase) - j sin(phase))
     *
     * so:
     *
     *   I_out = I*cos + Q*sin
     *   Q_out = Q*cos - I*sin
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
