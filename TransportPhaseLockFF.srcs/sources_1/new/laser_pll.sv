`timescale 1ns / 1ps
// ADC 224/3 -> coherent internal quadrature mixer -> FIR -> atan2 -> error.
// All ports, including GPIO controls, use the 245.76 MHz RF fabric clock.
module laser_pll #(
    parameter integer STAGE3_RANGE_SHIFT = 0
) (
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axis:m_axis:m_rf_axis:m_monitor:s_fra_tone:s_fra_ref:m_fra_error:m_fra_drive:m_fra_error_ref:m_fra_drive_ref, ASSOCIATED_RESET rst_n" *)
    input wire clk,
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *) input wire rst_n,
    input wire [127:0] s_axis_tdata,
    input wire s_axis_tvalid,
    output wire s_axis_tready,
    output wire [223:0] m_axis_tdata,
    output wire m_axis_tvalid,
    input wire m_axis_tready,
    input wire [31:0] rf_source_control,
    output wire [31:0] rf_source_status,
    output wire [223:0] m_rf_axis_tdata,
    output wire m_rf_axis_tvalid,
    input wire m_rf_axis_tready,
    input wire [31:0] frequency_low,
    input wire [31:0] frequency_high,
    input wire [31:0] control,
    input wire [31:0] phase_offset,
    input wire [31:0] acquisition_control,
    input wire [31:0] test_dc,
    input wire [31:0] tracking_control,
    input wire [31:0] monitor_control,
    output wire [31:0] tracking_status,
    output wire [31:0] monitor_status,
    output wire monitor_fifo_rst_n,
    output wire [127:0] m_monitor_tdata,
    output wire m_monitor_tvalid,
    input wire m_monitor_tready,
    output wire m_monitor_tlast,
    input wire [31:0] iir_control, iir_b0, iir_b1, iir_pole,
    output wire [31:0] iir_status,
    output wire [31:0] fra_clip_samples, fra_saturated_samples, fra_outside_clip_samples,
    output wire [31:0] fra_measured_samples, fra_error_extrema, fra_drive_extrema,
    input wire [31:0] fra_control, fra_settle_clocks, fra_measure_clocks,
    output wire [31:0] fra_status,
    input wire [159:0] s_fra_tone_tdata,
    input wire s_fra_tone_tvalid,
    output wire s_fra_tone_tready,
    input wire [271:0] s_fra_ref_tdata,
    input wire s_fra_ref_tvalid,
    output wire s_fra_ref_tready,
    output wire [159:0] m_fra_error_tdata, m_fra_drive_tdata,
    output wire m_fra_error_tvalid, m_fra_drive_tvalid,
    input wire m_fra_error_tready, m_fra_drive_tready,
    output wire [271:0] m_fra_error_ref_tdata, m_fra_drive_ref_tdata,
    output wire m_fra_error_ref_tvalid, m_fra_drive_ref_tvalid,
    input wire m_fra_error_ref_tready, m_fra_drive_ref_tready,
    output wire [31:0] phase_status,
    output wire [31:0] frequency_status,
    output wire [31:0] acquisition_status,
    output wire [31:0] fft_status
);
    wire enable = control[0];
    wire clear = control[3];
    wire [15:0] minimum_amplitude = control[31:16];
    wire [143:0] mixed_i, mixed_q;
    wire mixed_valid, frequency_ack;
    wire [47:0] committed_frequency;
    // NCO always runs, even while the phase detector/output are disabled.
    laser_pll_mixer mixer (
        .clk(clk), .rst_n(rst_n), .adc_data(s_axis_tdata), .adc_valid(s_axis_tvalid),
        .frequency_low(frequency_low), .frequency_high(frequency_high),
        .i_data(mixed_i), .q_data(mixed_q), .mixed_valid(mixed_valid),
        .frequency_ack(frequency_ack), .committed_frequency(committed_frequency)
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
    wire signed [15:0] dac_target, capture_target, unwrapped_target, output_target;
    wire error_valid, target_valid, target_saturated, saturated, stalled;
    wire capture_saturated, unwrapped_saturated, unwrapped_valid, output_valid, output_saturated, unwrap_arm;
    wire signed [23:0] turns;
    wire signed [42:0] unwrapped_phase;
    wire tracking_arm, tracking_valid, tracking_saturated;
    wire signed [15:0] tracking_target;
    laser_pll_error #(.STAGE3_RANGE_SHIFT(STAGE3_RANGE_SHIFT)) error_detector (.clk(clk), .rst_n(detector_rst_n),
        .measured_phase(measured_phase), .phase_valid(phase_valid),
        .control(control), .phase_offset(phase_offset), .unwrap_arm(unwrap_arm),
        .phase_error(phase_error),
        .frequency_error(frequency_error), .error_valid(error_valid),
        .dac_target(dac_target), .target_valid(target_valid), .target_saturated(target_saturated),
        .capture_target(capture_target), .capture_saturated(capture_saturated),
        .unwrapped_target(unwrapped_target), .unwrapped_saturated(unwrapped_saturated),
        .unwrapped_valid(unwrapped_valid), .turns(turns), .unwrapped_phase(unwrapped_phase));
    laser_pll_tracking #(.STAGE3_RANGE_SHIFT(STAGE3_RANGE_SHIFT)) tracking (.clk(clk), .rst_n(detector_rst_n), .arm(tracking_arm),
        .phase_codes(unwrapped_phase), .phase_valid(error_valid && unwrap_arm),
        .held_dac(output_target), .initial_gain_shift(control[7:4]), .invert(control[2]),
        .tracking_control(tracking_control), .dac_target(tracking_target),
        .target_valid(tracking_valid), .saturated(tracking_saturated), .tracking_status(tracking_status));
    laser_pll_monitor monitor (.clk(clk), .rst_n(rst_n),
        .i_sample(filtered_i), .q_sample(filtered_q),
        .sample_valid(filtered_valid && filtered_q_valid), .monitor_control(monitor_control),
        .monitor_status(monitor_status), .fifo_rst_n(monitor_fifo_rst_n),
        .m_axis_tdata(m_monitor_tdata), .m_axis_tvalid(m_monitor_tvalid),
        .m_axis_tready(m_monitor_tready), .m_axis_tlast(m_monitor_tlast));
    wire [9:0] fft_bin;
    wire fft_valid;
    laser_pll_fft coarse_estimator (.clk(clk), .rst_n(rst_n && !clear),
        .adc_data(s_axis_tdata), .adc_valid(s_axis_tvalid),
        .minimum_peak(acquisition_control[31:16]), .peak_bin(fft_bin),
        .estimate_valid(fft_valid), .fft_status(fft_status));
    laser_pll_acquisition acquisition (.clk(clk), .rst_n(detector_rst_n), .ready(m_axis_tready),
        .acquisition_control(acquisition_control), .test_dc(test_dc), .control(control),
        .reference_frequency(committed_frequency), .fft_bin(fft_bin), .fft_valid(fft_valid),
        .error_valid(error_valid),
        .legacy_target(dac_target), .legacy_saturated(target_saturated),
        .capture_target(capture_target), .capture_saturated(capture_saturated),
        .unwrapped_target(unwrapped_target), .unwrapped_saturated(unwrapped_saturated),
        .unwrapped_valid(unwrapped_valid),
        .tracking_target(tracking_target), .tracking_saturated(tracking_saturated), .tracking_valid(tracking_valid),
        .target_valid(target_valid), .turns(turns), .unwrap_arm(unwrap_arm), .tracking_arm(tracking_arm),
        .dac_target(output_target), .output_valid(output_valid),
        .output_saturated(output_saturated), .acquisition_status(acquisition_status));
    wire signed [15:0] compensated_target;
    wire compensated_valid, compensated_saturated;
    laser_pll_iir compensator (.clk(clk), .rst_n(rst_n),
        .input_code(output_target), .input_valid(output_valid), .input_saturated(output_saturated),
        .control(iir_control), .b0_word(iir_b0), .b1_word(iir_b1), .pole_word(iir_pole),
        .output_code(compensated_target), .output_valid(compensated_valid),
        .output_saturated(compensated_saturated), .status(iir_status));
    wire signed [15:0] driven_target;
    wire driven_saturated;
    wire signed [19:0] rf_phase_command;
    wire signed [17:0] rf_applied_phase;
    assign rf_source_status=32'h52463701; // RF7 feature layout revision 1, separate from A7 PLL ABI.
    laser_pll_rf_pm rf_stimulus (.clk(clk), .rst_n(rst_n), .phase_command(rf_phase_command),
        .amplitude(rf_source_control[15:0]), .m_axis_tdata(m_rf_axis_tdata),
        .m_axis_tvalid(m_rf_axis_tvalid), .m_axis_tready(m_rf_axis_tready), .applied_phase(rf_applied_phase));
    // Register each lane's diagnostic near the ADC, avoiding a long path from
    // the converter through eight comparisons into the FRA counter enables.
    reg [7:0] adc_lane_clipped;
    wire raw_adc_clipped=|adc_lane_clipped;
    always @(posedge clk) begin
        if (!rst_n) adc_lane_clipped<=0;
        else for (integer lane=0;lane<8;lane=lane+1)
            adc_lane_clipped[lane]<=s_axis_tvalid &&
                ($signed(s_axis_tdata[16*lane+:16])>=32752 ||
                 $signed(s_axis_tdata[16*lane+:16])<=-32752);
    end
    laser_pll_fra loop_measurement (.clk(clk), .rst_n(rst_n),
        .error_code(compensated_target), .error_valid(compensated_valid), .error_saturated(compensated_saturated),
        .dac_ready(m_axis_tready), .phase_valid(error_valid),
        .measured_phase(measured_phase), .measured_phase_valid(phase_valid), .raw_adc_clipped(raw_adc_clipped),
        .rf_applied_phase(rf_applied_phase), .rf_ready(m_rf_axis_tready), .rf_phase_command(rf_phase_command),
        .control(fra_control), .settle_clocks(fra_settle_clocks), .measure_clocks(fra_measure_clocks),
        .clip_samples(fra_clip_samples), .saturated_samples(fra_saturated_samples),
        .outside_clip_samples(fra_outside_clip_samples), .measured_samples(fra_measured_samples),
        .error_extrema(fra_error_extrema), .drive_extrema(fra_drive_extrema),
        .status(fra_status), .drive_code(driven_target), .drive_saturated(driven_saturated),
        .s_tone_tdata(s_fra_tone_tdata), .s_tone_tvalid(s_fra_tone_tvalid), .s_tone_tready(s_fra_tone_tready),
        .s_ref_tdata(s_fra_ref_tdata), .s_ref_tvalid(s_fra_ref_tvalid), .s_ref_tready(s_fra_ref_tready),
        .m_error_tdata(m_fra_error_tdata), .m_error_tvalid(m_fra_error_tvalid), .m_error_tready(m_fra_error_tready),
        .m_drive_tdata(m_fra_drive_tdata), .m_drive_tvalid(m_fra_drive_tvalid), .m_drive_tready(m_fra_drive_tready),
        .m_error_ref_tdata(m_fra_error_ref_tdata), .m_error_ref_tvalid(m_fra_error_ref_tvalid), .m_error_ref_tready(m_fra_error_ref_tready),
        .m_drive_ref_tdata(m_fra_drive_ref_tdata), .m_drive_ref_tvalid(m_fra_drive_ref_tvalid), .m_drive_ref_tready(m_fra_drive_ref_tready));
    laser_pll_dac dac_output (.clk(clk), .rst_n(rst_n), .enable(enable), .clear(clear),
        .dac_target(driven_target), .target_valid(compensated_valid), .target_saturated(driven_saturated),
        .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready),
        .saturated(saturated), .stalled(stalled));
    // Previously reserved status bits expose the actual stage-3 scale. The
    // coefficient/gain-ramp ABI stays unchanged: span = 160 * 2^shift turns.
    localparam [3:0] RANGE_STATUS = STAGE3_RANGE_SHIFT;
    assign phase_status = {5'b0, RANGE_STATUS, frequency_ack, stalled, saturated, error_valid,
                           enable, phase_error};
    assign frequency_status = {{14{frequency_error[17]}},frequency_error};
endmodule
