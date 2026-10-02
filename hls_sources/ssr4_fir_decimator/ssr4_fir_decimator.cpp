#include "ssr4_fir_decimator.h"

typedef ap_int<16> sample_t;
typedef ap_int<18> coeff_t;
typedef ap_int<18> pair_sum_t;
typedef ap_int<56> acc_t;

#include "fir_coeffs.h"

static sample_t unpack_lane(ssr4_axis_t word, int lane) {
#pragma HLS INLINE
    ap_uint<16> bits =
        word.range(lane * SSR4_FIR_SAMPLE_BITS + 15,
                   lane * SSR4_FIR_SAMPLE_BITS);
    return (sample_t)bits;
}

static scalar_axis_t round_to_i32(acc_t acc) {
#pragma HLS INLINE
    const acc_t round = ((acc_t)1) << (SSR4_FIR_COEFF_FRAC_BITS - 1);
    acc_t shifted = (acc + round) >> SSR4_FIR_COEFF_FRAC_BITS;

    if (shifted > 2147483647LL) {
        return 2147483647;
    }
    if (shifted < -2147483648LL) {
        return (scalar_axis_t)0x80000000;
    }

    return (scalar_axis_t)shifted;
}

void ssr4_fir_decimator(
    hls::stream<ssr4_axis_t> &s_axis,
    hls::stream<scalar_axis_t> &m_axis,
    bool clear) {
#pragma HLS INTERFACE axis port=s_axis
#pragma HLS INTERFACE axis port=m_axis
#pragma HLS INTERFACE ap_none port=clear
#pragma HLS INTERFACE ap_ctrl_none port=return
#pragma HLS PIPELINE II=1
#pragma HLS ARRAY_PARTITION variable=FIR_COEFFS complete dim=1

    static sample_t history[SSR4_FIR_TAPS];
#pragma HLS ARRAY_PARTITION variable=history complete dim=1
    static ap_uint<9> valid_samples = 0;

    if (clear) {
    CLEAR_HISTORY:
        for (int i = 0; i < SSR4_FIR_TAPS; i++) {
#pragma HLS UNROLL
            history[i] = 0;
        }
        valid_samples = 0;
        return;
    }

    ssr4_axis_t input_word = s_axis.read();

SHIFT_HISTORY:
    for (int i = SSR4_FIR_TAPS - 1; i >= SSR4_FIR_LANES; i--) {
#pragma HLS UNROLL
        history[i] = history[i - SSR4_FIR_LANES];
    }

INSERT_LANES:
    for (int lane = 0; lane < SSR4_FIR_LANES; lane++) {
#pragma HLS UNROLL
        history[SSR4_FIR_LANES - 1 - lane] = unpack_lane(input_word, lane);
    }

    if (valid_samples < SSR4_FIR_TAPS) {
        valid_samples += SSR4_FIR_LANES;
        if (valid_samples > SSR4_FIR_TAPS) {
            valid_samples = SSR4_FIR_TAPS;
        }
    }

    acc_t acc = 0;

SYMMETRIC_MAC:
    for (int tap = 0; tap < (SSR4_FIR_TAPS / 2); tap++) {
#pragma HLS UNROLL
        pair_sum_t sample_pair = history[tap] + history[SSR4_FIR_TAPS - 1 - tap];
        acc += (acc_t)sample_pair * (coeff_t)FIR_COEFFS[tap];
    }

    acc += (acc_t)history[SSR4_FIR_TAPS / 2] * (coeff_t)FIR_COEFFS[SSR4_FIR_TAPS / 2];

    if (valid_samples == SSR4_FIR_TAPS) {
        m_axis.write(round_to_i32(acc));
    }
}
