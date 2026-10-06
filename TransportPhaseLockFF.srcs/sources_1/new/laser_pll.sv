`timescale 1ns / 1ps
// ADC 224/3 -> coherent internal quadrature mixer -> FIR -> atan2 -> error.
// All ports, including GPIO controls, use the 245.76 MHz RF fabric clock.
module laser_pll (
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axis:m_axis, ASSOCIATED_RESET rst_n" *)
    input wire clk,
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *) input wire rst_n,
    input wire [127:0] s_axis_tdata,
    input wire s_axis_tvalid,
    output wire s_axis_tready,
    output wire [223:0] m_axis_tdata,
    output wire m_axis_tvalid,
    input wire m_axis_tready,
    input wire [31:0] frequency_low,
    input wire [31:0] frequency_high,
    input wire [31:0] control,
    input wire [31:0] phase_offset,
    output wire [31:0] phase_status,
    output wire [31:0] frequency_status
);
    wire enable = control[0];
    wire clear = control[3];
    wire [15:0] minimum_amplitude = control[31:16];
    wire [143:0] mixed_i, mixed_q;
    wire mixed_valid, frequency_ack;
    // NCO always runs, even while the phase detector/output are disabled.
    laser_pll_mixer mixer (
        .clk(clk), .rst_n(rst_n), .adc_data(s_axis_tdata), .adc_valid(s_axis_tvalid),
        .frequency_low(frequency_low), .frequency_high(frequency_high),
        .i_data(mixed_i), .q_data(mixed_q), .mixed_valid(mixed_valid),
        .frequency_ack(frequency_ack)
    );
    assign s_axis_tready = 1'b1;
    wire detector_rst_n = rst_n && enable && !clear;
    wire signed [23:0] filtered_i, filtered_q;
    wire filtered_valid, filtered_q_valid;
    laser_pll_fir filter_i (.clk(clk), .rst_n(detector_rst_n), .samples(mixed_i),
        .samples_valid(mixed_valid), .filtered(filtered_i), .filtered_valid(filtered_valid));
    laser_pll_fir filter_q (.clk(clk), .rst_n(detector_rst_n), .samples(mixed_q),
        .samples_valid(mixed_valid), .filtered(filtered_q), .filtered_valid(filtered_q_valid));
    wire [23:0] abs_i = filtered_i[23] ? -filtered_i : filtered_i;
    wire [23:0] abs_q = filtered_q[23] ? -filtered_q : filtered_q;
    // Max norm avoids a square root. Threshold is post-mixer ADC counts;
    // for a sinusoid the mixed vector amplitude is approximately ADC peak/2.
    wire amplitude_good = ((abs_i >= {minimum_amplitude,8'b0}) ||
                           (abs_q >= {minimum_amplitude,8'b0})) && (abs_i != 0 || abs_q != 0);
    wire signed [17:0] measured_phase;
    wire phase_valid;
    laser_pll_cordic phase_extractor (.clk(clk), .rst_n(detector_rst_n),
        .i_sample(filtered_i), .q_sample(filtered_q),
        .sample_valid(filtered_valid && filtered_q_valid && amplitude_good),
        .phase(measured_phase), .phase_valid(phase_valid));

    wire signed [17:0] phase_error, frequency_error;
    wire signed [15:0] dac_target;
    wire error_valid, target_valid, target_saturated, saturated, stalled;
    laser_pll_error error_detector (.clk(clk), .rst_n(detector_rst_n),
        .measured_phase(measured_phase), .phase_valid(phase_valid),
        .control(control), .phase_offset(phase_offset), .phase_error(phase_error),
        .frequency_error(frequency_error), .error_valid(error_valid),
        .dac_target(dac_target), .target_valid(target_valid), .target_saturated(target_saturated));
    laser_pll_dac dac_output (.clk(clk), .rst_n(rst_n), .enable(enable), .clear(clear),
        .dac_target(dac_target), .target_valid(target_valid), .target_saturated(target_saturated),
        .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready),
        .saturated(saturated), .stalled(stalled));
    assign phase_status = {9'b0, frequency_ack, stalled, saturated, error_valid,
                           enable, phase_error};
    assign frequency_status = {{14{frequency_error[17]}},frequency_error};
endmodule
