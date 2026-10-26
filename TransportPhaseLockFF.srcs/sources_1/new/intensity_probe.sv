`timescale 1ns / 1ps
// Nonblocking intensity calibration/FRA tap; the existing PI is untouched.
// Record: {DDS phase u32, delivered command i16, selected PI/manual command i16,
//          raw ADC I lane3 i16, lane2 i16, lane1 i16, lane0 i16}.
// Raw samples are selected, NOT temporally averaged: sensor calibration must
// precede averaging in Python. Frame interval is 2^D / 245.76 MHz.
module intensity_probe (
    input wire clk, rst_n,
    input wire [63:0] adc_bus,
    input wire adc_valid, dac_ready,
    input wire signed [15:0] controller_command, manual_command,
    input wire manual_enable,
    output wire [15:0] command_out,
    input wire [31:0] control, frequency_word, amplitude_word, limits,
    output wire [31:0] status, feature_version,
    output reg [31:0] clip_samples, invalid_samples,
    output wire fifo_rst_n,
    output reg [127:0] m_axis_tdata,
    output reg m_axis_tvalid, m_axis_tlast,
    input wire m_axis_tready
);
    wire signed [17:0] dither;
    wire [31:0] dither_phase;
    wire tone_active, tone_ramping;
    intensity_tone tone (.clk(clk),.rst_n(rst_n),.enable(control[0]),
        .frequency_word(frequency_word),.amplitude_codes(amplitude_word[15:0]),
        .dither(dither),.dither_phase(dither_phase),.active(tone_active),.ramping(tone_ramping));
    // The HLS PI has combinational output saturation. Register its boundary so
    // that saturation and the diagnostic add/limit logic occupy separate clocks.
    // This adds one feedback clock (4.069 ns), in both idle and diagnostic modes.
    reg signed [15:0] selected;
    reg selected_manual;
    always @(posedge clk) begin
        if (!rst_n) begin selected<=0; selected_manual<=0; end
        else begin
            selected<=manual_enable ? manual_command : controller_command;
            selected_manual<=manual_enable;
        end
    end
    wire signed [18:0] sum=$signed(selected)+$signed(dither);
    wire signed [18:0] minimum=$signed({1'b0,limits[15:0]});
    wire signed [18:0] maximum=$signed({1'b0,limits[31:16]});
    wire clipped=tone_active && (sum<minimum || sum>maximum);
    // At idle the command is unchanged in value, delayed by the boundary clock.
    assign command_out=!tone_active ? selected : sum<minimum ? limits[15:0] :
                       sum>maximum ? limits[31:16] : sum[15:0];
    assign feature_version=32'h494e5401; // INT, measurement ABI 1
    wire armed=control[1];
    assign fifo_rst_n=rst_n && armed;
    reg started, collecting, done;
    reg overflow_seen, invalid_seen, clip_seen, controller_rail_seen, adc_rail_seen, changed_seen;
    reg [4:0] decimation_log2;
    reg [19:0] count, sample_limit;
    reg [20:0] interval_count;
    wire [20:0] interval_mask=(22'd1 << decimation_log2)-1'b1;
    reg [31:0] saved_frequency, saved_amplitude, saved_limits, saved_control;
    // Rail diagnostics are a side path. Delay the window with the ADC word so
    // the first/last checked samples still belong to exactly this capture.
    reg [63:0] adc_for_rail;
    reg rail_window;
    always @(posedge clk) begin
        if (!rst_n) begin adc_for_rail<=0; rail_window<=0; end
        else begin adc_for_rail<=adc_bus; rail_window<=armed && collecting; end
    end
    wire adc_rail=($signed(adc_for_rail[15:0])>=32752 || $signed(adc_for_rail[15:0])<=-32752 ||
                  $signed(adc_for_rail[31:16])>=32752 || $signed(adc_for_rail[31:16])<=-32752 ||
                  $signed(adc_for_rail[47:32])>=32752 || $signed(adc_for_rail[47:32])<=-32752 ||
                  $signed(adc_for_rail[63:48])>=32752 || $signed(adc_for_rail[63:48])<=-32752);
    assign status={count,2'b0,changed_seen,tone_active,tone_ramping,adc_rail_seen,
                   controller_rail_seen,clip_seen,invalid_seen,overflow_seen,done,collecting};
    always @(posedge clk) begin
        if (!rst_n || !armed) begin
            started<=0; collecting<=0; done<=0; count<=0; sample_limit<=0;
            interval_count<=0; decimation_log2<=0;
            overflow_seen<=0; invalid_seen<=0; clip_seen<=0; controller_rail_seen<=0;
            adc_rail_seen<=0; changed_seen<=0; clip_samples<=0; invalid_samples<=0;
            saved_frequency<=0; saved_amplitude<=0; saved_limits<=0; saved_control<=0;
            m_axis_tvalid<=0; m_axis_tlast<=0; m_axis_tdata<=0;
        end else begin
            if (!started) begin
                started<=1; collecting<=control[31:12]!=0;
                sample_limit<=control[31:12];
                decimation_log2<=control[7:3]>20 ? 5'd20 : control[7:3];
                saved_frequency<=frequency_word; saved_amplitude<=amplitude_word;
                saved_limits<=limits; saved_control<=control;
            end
            if (m_axis_tvalid && m_axis_tready) begin
                m_axis_tvalid<=0;
                if (m_axis_tlast) done<=1;
            end
            if (rail_window && adc_rail) adc_rail_seen<=1;
            if (collecting) begin
                if (control!=saved_control || frequency_word!=saved_frequency ||
                    amplitude_word!=saved_amplitude || limits!=saved_limits) changed_seen<=1;
                if (!adc_valid || !dac_ready) begin
                    invalid_seen<=1; invalid_samples<=invalid_samples+1'b1;
                end
                if (clipped) begin clip_seen<=1; clip_samples<=clip_samples+1'b1; end
                if (!selected_manual && (selected<=0 || selected>=32767)) controller_rail_seen<=1;
                if (interval_count==interval_mask) begin
                    interval_count<=0;
                    if (!m_axis_tvalid || m_axis_tready) begin
                        m_axis_tdata<={dither_phase,command_out,selected,adc_bus};
                        m_axis_tvalid<=1; m_axis_tlast<=count==sample_limit-1'b1;
                        count<=count+1'b1;
                        if (count==sample_limit-1'b1) collecting<=0;
                    end else overflow_seen<=1;
                end else interval_count<=interval_count+1'b1;
            end
        end
    end
endmodule
