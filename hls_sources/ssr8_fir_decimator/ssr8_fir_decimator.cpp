#include "ssr8_fir_decimator.h"

typedef ap_int<16> sample_t;
typedef ap_int<18> coeff_t;
typedef ap_int<18> pair_sum_t;
typedef ap_int<56> acc_t;

/*
 * Default coefficient set:
 *
 *   255-tap symmetric Kaiser-windowed low-pass FIR
 *   input sample rate: 1966.08 MS/s, from 245.76 MHz * 8 lanes
 *   intended decimation: 8
 *   passband planning edge: about 60 MHz
 *   first alias stopband edge: 122.88 MHz
 *   coefficient format: signed Q1.17, sum exactly 2^17
 *
 * Because the coefficients are symmetric, the implementation uses only the
 * first 128 taps in the multiply loop.
 */
static const coeff_t FIR_COEFFS[SSR8_FIR_TAPS] = {
          0,      -1,      -1,      -2,      -2,      -2,      -2,      -2,
         -1,       0,       2,       3,       5,       7,       8,       8,
          8,       7,       5,       2,      -2,      -7,     -12,     -16,
        -20,     -22,     -23,     -21,     -17,     -11,      -2,       8,
         19,      30,      40,      47,      51,      51,      45,      35,
         19,       0,     -22,     -45,     -66,     -84,     -96,    -101,
        -97,     -83,     -60,     -28,      10,      52,      93,     131,
        160,     178,     182,     169,     138,      93,      33,     -35,
       -108,    -178,    -238,    -283,    -306,    -304,    -273,    -215,
       -131,     -28,      88,     207,     318,     411,     475,     502,
        486,     424,     318,     173,       0,    -190,    -380,    -553,
       -691,    -780,    -807,    -763,    -646,    -459,    -213,      76,
        386,     691,     964,    1178,    1306,    1329,    1234,    1016,
        681,     246,    -262,    -809,   -1350,   -1838,   -2223,   -2458,
      -2500,   -2317,   -1887,   -1201,    -269,     887,    2228,    3701,
       5242,    6782,    8247,    9564,   10667,   11499,   12017,   12194,
      12017,   11499,   10667,    9564,    8247,    6782,    5242,    3701,
       2228,     887,    -269,   -1201,   -1887,   -2317,   -2500,   -2458,
      -2223,   -1838,   -1350,    -809,    -262,     246,     681,    1016,
       1234,    1329,    1306,    1178,     964,     691,     386,      76,
       -213,    -459,    -646,    -763,    -807,    -780,    -691,    -553,
       -380,    -190,       0,     173,     318,     424,     486,     502,
        475,     411,     318,     207,      88,     -28,    -131,    -215,
       -273,    -304,    -306,    -283,    -238,    -178,    -108,     -35,
         33,      93,     138,     169,     182,     178,     160,     131,
         93,      52,      10,     -28,     -60,     -83,     -97,    -101,
        -96,     -84,     -66,     -45,     -22,       0,      19,      35,
         45,      51,      51,      47,      40,      30,      19,       8,
         -2,     -11,     -17,     -21,     -23,     -22,     -20,     -16,
        -12,      -7,      -2,       2,       5,       7,       8,       8,
          8,       7,       5,       3,       2,       0,      -1,      -2,
         -2,      -2,      -2,      -2,      -1,      -1,       0
};

static sample_t unpack_lane(ssr8_axis_t word, int lane) {
#pragma HLS INLINE
    ap_uint<16> bits =
        word.range(lane * SSR8_FIR_SAMPLE_BITS + 15,
                   lane * SSR8_FIR_SAMPLE_BITS);
    return (sample_t)bits;
}

static scalar_axis_t round_to_i32(acc_t acc) {
#pragma HLS INLINE
    const acc_t round = ((acc_t)1) << (SSR8_FIR_COEFF_FRAC_BITS - 1);
    acc_t shifted = (acc + round) >> SSR8_FIR_COEFF_FRAC_BITS;

    if (shifted > 2147483647LL) {
        return 2147483647;
    }
    if (shifted < -2147483648LL) {
        return (scalar_axis_t)0x80000000;
    }

    return (scalar_axis_t)shifted;
}

void ssr8_fir_decimator(
    hls::stream<ssr8_axis_t> &s_axis,
    hls::stream<scalar_axis_t> &m_axis,
    bool clear) {
#pragma HLS INTERFACE axis port=s_axis
#pragma HLS INTERFACE axis port=m_axis
#pragma HLS INTERFACE ap_none port=clear
#pragma HLS INTERFACE ap_ctrl_none port=return
#pragma HLS PIPELINE II=1
#pragma HLS ARRAY_PARTITION variable=FIR_COEFFS complete dim=1

    static sample_t history[SSR8_FIR_TAPS];
#pragma HLS ARRAY_PARTITION variable=history complete dim=1
    static ap_uint<9> valid_samples = 0;

    if (clear) {
    CLEAR_HISTORY:
        for (int i = 0; i < SSR8_FIR_TAPS; i++) {
#pragma HLS UNROLL
            history[i] = 0;
        }
        valid_samples = 0;
        return;
    }

    ssr8_axis_t input_word = s_axis.read();

SHIFT_HISTORY:
    for (int i = SSR8_FIR_TAPS - 1; i >= SSR8_FIR_LANES; i--) {
#pragma HLS UNROLL
        history[i] = history[i - SSR8_FIR_LANES];
    }

INSERT_LANES:
    for (int lane = 0; lane < SSR8_FIR_LANES; lane++) {
#pragma HLS UNROLL
        history[SSR8_FIR_LANES - 1 - lane] = unpack_lane(input_word, lane);
    }

    if (valid_samples < SSR8_FIR_TAPS) {
        valid_samples += SSR8_FIR_LANES;
        if (valid_samples > SSR8_FIR_TAPS) {
            valid_samples = SSR8_FIR_TAPS;
        }
    }

    acc_t acc = 0;

SYMMETRIC_MAC:
    for (int tap = 0; tap < (SSR8_FIR_TAPS / 2); tap++) {
#pragma HLS UNROLL
        pair_sum_t sample_pair = history[tap] + history[SSR8_FIR_TAPS - 1 - tap];
        acc += (acc_t)sample_pair * FIR_COEFFS[tap];
    }

    acc += (acc_t)history[SSR8_FIR_TAPS / 2] * FIR_COEFFS[SSR8_FIR_TAPS / 2];

    if (valid_samples == SSR8_FIR_TAPS) {
        m_axis.write(round_to_i32(acc));
    }
}
