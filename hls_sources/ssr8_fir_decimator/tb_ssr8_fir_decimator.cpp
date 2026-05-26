#include <cstdlib>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>

#include "ssr8_fir_decimator.h"

static void pack_lane(ssr8_axis_t &word, int lane, ap_int<16> sample) {
    word.range(lane * SSR8_FIR_SAMPLE_BITS + 15,
               lane * SSR8_FIR_SAMPLE_BITS) = (ap_uint<16>)sample;
}

static ssr8_axis_t make_constant_bus(ap_int<16> sample) {
    ssr8_axis_t word = 0;
    for (int lane = 0; lane < SSR8_FIR_LANES; lane++) {
        pack_lane(word, lane, sample);
    }
    return word;
}

static ap_int<16> clamp_to_i16(double value) {
    long rounded = std::lround(value);
    if (rounded > 32767) {
        return 32767;
    }
    if (rounded < -32768) {
        return -32768;
    }
    return (ap_int<16>)rounded;
}

static ssr8_axis_t make_plot_bus(int beat) {
    ssr8_axis_t word = 0;

    const double fs_in_hz = 1966.08e6;
    const double two_pi = 6.28318530717958647692;
    const double pass_hz = 10.0e6;
    const double stop_hz = 180.0e6;

    for (int lane = 0; lane < SSR8_FIR_LANES; lane++) {
        const int n = beat * SSR8_FIR_LANES + lane;
        const double pass_tone = 10000.0 * std::sin(two_pi * pass_hz * n / fs_in_hz);
        const double stop_tone = 7000.0 * std::sin(two_pi * stop_hz * n / fs_in_hz);

        pack_lane(word, lane, clamp_to_i16(pass_tone + stop_tone));
    }

    return word;
}

static ssr8_axis_t make_sine_scan_bus(int beat, double freq_hz, double amplitude) {
    ssr8_axis_t word = 0;

    const double fs_in_hz = 1966.08e6;
    const double two_pi = 6.28318530717958647692;

    for (int lane = 0; lane < SSR8_FIR_LANES; lane++) {
        const int n = beat * SSR8_FIR_LANES + lane;
        const double sample = amplitude * std::cos(two_pi * freq_hz * n / fs_in_hz);
        pack_lane(word, lane, clamp_to_i16(sample));
    }

    return word;
}

static ap_int<16> newest_lane_sample(ssr8_axis_t word) {
    ap_uint<16> bits = word.range(127, 112);
    return (ap_int<16>)bits;
}

static void write_plot_csv() {
    hls::stream<ssr8_axis_t> s_axis("plot_s_axis");
    hls::stream<scalar_axis_t> m_axis("plot_m_axis");

    const int plot_beats = 8192;
    std::ofstream csv("csim_filter_results.csv");

    csv << "beat,input_newest,output_valid,output_sample\n";

    ssr8_fir_decimator(s_axis, m_axis, true);

    for (int beat = 0; beat < plot_beats; beat++) {
        ssr8_axis_t input_word = make_plot_bus(beat);
        s_axis.write(input_word);
        ssr8_fir_decimator(s_axis, m_axis, false);

        bool valid = !m_axis.empty();
        scalar_axis_t y = 0;
        if (valid) {
            y = m_axis.read();
        }

        csv << beat << ","
            << newest_lane_sample(input_word).to_int() << ","
            << (valid ? 1 : 0) << ","
            << (valid ? y.to_int() : 0) << "\n";
    }

    csv.close();
    std::cout << "Wrote csim_filter_results.csv\n";
}

static void write_frequency_response_csv() {
    const double fs_in_hz = 1966.08e6;
    const double fs_out_hz = 245.76e6;
    const double two_pi = 6.28318530717958647692;
    const double input_amplitude = 12000.0;

    const int frequency_points = 512;
    const int discard_valid_outputs = 64;
    const int measured_valid_outputs = 1024;
    const int warmup_beats = (SSR8_FIR_TAPS + SSR8_FIR_LANES - 1) / SSR8_FIR_LANES;

    std::ofstream csv("csim_frequency_response.csv");
    csv << "freq_hz,normalized_input_freq,input_amplitude,output_amplitude,gain_db,valid_samples\n";
    csv << std::setprecision(12);

    for (int point = -1; point < frequency_points; point++) {
        /*
         * point = -1 measures true DC. The remaining points are half-bin
         * spaced across the input Nyquist band. That avoids exact aliases at
         * multiples of the output sample rate, where a real-only sine scan can
         * become phase-dependent after decimation.
         */
        const double freq_hz =
            (point < 0) ? 0.0 : (0.5 * fs_in_hz) * (point + 0.5) / frequency_points;
        const double omega_out = two_pi * freq_hz / fs_out_hz;

        hls::stream<ssr8_axis_t> s_axis("scan_s_axis");
        hls::stream<scalar_axis_t> m_axis("scan_m_axis");

        ssr8_fir_decimator(s_axis, m_axis, true);

        int beat = 0;
        int valid_count = 0;
        int measured_count = 0;
        double sum_i = 0.0;
        double sum_q = 0.0;

        while (measured_count < measured_valid_outputs) {
            s_axis.write(make_sine_scan_bus(beat, freq_hz, input_amplitude));
            ssr8_fir_decimator(s_axis, m_axis, false);

            if (!m_axis.empty()) {
                scalar_axis_t y = m_axis.read();

                if (valid_count >= discard_valid_outputs) {
                    const double angle = omega_out * measured_count;
                    const double y_double = (double)y.to_int();
                    sum_i += y_double * std::cos(angle);
                    sum_q -= y_double * std::sin(angle);
                    measured_count++;
                }

                valid_count++;
            }

            beat++;

            /*
             * A guard for C simulation. This should never trigger unless the
             * DUT stops producing output.
             */
            if (beat > warmup_beats + discard_valid_outputs + measured_valid_outputs + 128) {
                break;
            }
        }

        const double magnitude = std::sqrt(sum_i * sum_i + sum_q * sum_q);
        const double cycles_per_output = freq_hz / fs_out_hz;
        const double nearest_integer = std::floor(cycles_per_output + 0.5);
        const double alias_distance = std::abs(cycles_per_output - nearest_integer);
        const bool aliases_to_dc = alias_distance < 1.0e-9;
        const bool aliases_to_nyquist = std::abs(alias_distance - 0.5) < 1.0e-9;
        const double scale = (aliases_to_dc || aliases_to_nyquist) ? 1.0 : 2.0;
        const double output_amplitude =
            (measured_count > 0) ? scale * magnitude / measured_count : 0.0;
        const double gain = output_amplitude / input_amplitude;
        const double gain_db = 20.0 * std::log10((gain > 1.0e-15) ? gain : 1.0e-15);

        csv << freq_hz << ","
            << freq_hz / (0.5 * fs_in_hz) << ","
            << input_amplitude << ","
            << output_amplitude << ","
            << gain_db << ","
            << measured_count << "\n";
    }

    csv.close();
    std::cout << "Wrote csim_frequency_response.csv\n";
}

int main() {
    hls::stream<ssr8_axis_t> s_axis("s_axis");
    hls::stream<scalar_axis_t> m_axis("m_axis");

    const int input_beats = 80;
    const int warmup_beats = (SSR8_FIR_TAPS + SSR8_FIR_LANES - 1) / SSR8_FIR_LANES;
    const ap_int<16> dc_value = 1234;
    int errors = 0;

    ssr8_fir_decimator(s_axis, m_axis, true);

    for (int beat = 0; beat < input_beats; beat++) {
        s_axis.write(make_constant_bus(dc_value));
        ssr8_fir_decimator(s_axis, m_axis, false);

        if (beat + 1 < warmup_beats) {
            if (!m_axis.empty()) {
                std::cerr << "FAIL: output appeared before FIR history filled\n";
                errors++;
            }
        } else {
            if (m_axis.empty()) {
                std::cerr << "FAIL: missing output after warmup at beat " << beat << "\n";
                errors++;
            } else {
                scalar_axis_t y = m_axis.read();
                int error = std::abs(y.to_int() - dc_value.to_int());
                if (error > 1) {
                    std::cerr << "FAIL: DC gain error at beat " << beat
                              << " y=" << y.to_int()
                              << " expected=" << dc_value.to_int() << "\n";
                    errors++;
                }
            }
        }
    }

    ssr8_fir_decimator(s_axis, m_axis, true);
    if (!m_axis.empty()) {
        std::cerr << "FAIL: clear produced an output sample\n";
        errors++;
    }

    if (errors == 0) {
        write_plot_csv();
        write_frequency_response_csv();
        std::cout << "PASS\n";
    }

    return errors;
}
