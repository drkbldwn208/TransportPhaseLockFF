#include <cstdint>
#include <iostream>
#include <vector>
#include "ssr4_fir_decimator.h"
#include "fir_coeffs.h"

// Independent, nonsymmetric convolution in ordinary integer arithmetic.
static int reference(const std::vector<int> &samples, int n) {
    int64_t sum = 0;
    for (int tap = 0; tap < SSR4_FIR_TAPS; tap++)
        sum += (int64_t)samples[n - tap] * FIR_COEFFS[tap];
    sum += 1LL << 16;
    // Explicit floor division, including negative values.
    return sum >= 0 ? sum / (1LL << 17)
                    : -((-sum + (1LL << 17) - 1) / (1LL << 17));
}

int main() {
    hls::stream<ssr4_axis_t> input;
    hls::stream<scalar_axis_t> output;
    int errors = 0;
    int coeff_sum = 0;
    for (int i = 0; i < SSR4_FIR_TAPS; i++) {
        coeff_sum += FIR_COEFFS[i];
        if (FIR_COEFFS[i] != FIR_COEFFS[SSR4_FIR_TAPS - 1 - i]) errors++;
    }
    if (coeff_sum != (1 << 17)) errors++;

    uint32_t rng = 12345;
    // Repeated clear checks also verify that a new capture has no old history.
    for (int test = 0; test < 8; test++) {
        std::vector<int> samples;
        ssr4_axis_t first_word = 0;
        input.write(first_word);
        ssr4_fir_decimator(input, output, true);
        if (input.empty() || !output.empty()) return 1;
        input.read();

        for (int beat = 0; beat < 160; beat++) {
            ssr4_axis_t word = 0;
            for (int lane = 0; lane < 4; lane++) {
                const int n = 4 * beat + lane;
                rng = 1664525U * rng + 1013904223U;
                int value;
                if (test == 0) value = 1234;
                else if (test == 1) value = -32768;
                else if (test == 2) value = 32767;
                else if (test == 3) value = (int)(rng >> 16) - 32768;
                else value = n == 320 + test - 4 ? 32767 : 0;
                samples.push_back(value);
                word.range(16 * lane + 15, 16 * lane) = (ap_uint<16>)value;
            }
            input.write(word);
            ssr4_fir_decimator(input, output, false);
            if (!input.empty()) return 1;
            const bool expected_valid = beat >= 63;
            if (output.empty() == expected_valid) {
                std::cerr << "FAIL: output count at beat " << beat << "\n";
                return 1;
            }
            if (expected_valid) {
                scalar_axis_t word_out = output.read();
                const int expected = reference(samples, 4 * beat + 3);
                if (word_out.to_int() != expected) {
                    if (errors < 10)
                        std::cerr << "FAIL: test=" << test << " beat=" << beat
                                  << " got=" << word_out
                                  << " expected=" << expected << "\n";
                    errors++;
                }
                if (!output.empty()) return 1;
            }
        }
    }
    std::cout << (errors ? "FAIL" : "PASS")
              << ": DC, signed extremes, random convolution, all four impulse lanes, reset/startup\n";
    return errors ? 1 : 0;
}
