// Timing-only source/sink registers model synchronous RFDC/GPIO boundaries.
// These registers are NOT part of the PLL or its quoted pipeline latency.
module laser_pll_timing_top (
    input wire clk,
    input wire rst_n,
    input wire [127:0] adc_data,
    input wire adc_valid,
    input wire dac_ready,
    input wire [31:0] frequency_low, frequency_high, control, phase_offset,
    input wire [31:0] acquisition_control, test_dc,
    input wire [31:0] tracking_control, monitor_control,
    input wire monitor_ready,
    output reg [127:0] monitor_data,
    output reg monitor_valid, monitor_last, monitor_reset,
    output reg [31:0] tracking_status, monitor_status,
    output reg [223:0] dac_data,
    output reg dac_valid, adc_ready,
    output reg [31:0] phase_status, frequency_status, acquisition_status, fft_status
);
    reg reset_reg, valid_reg, ready_reg;
    reg [127:0] data_reg;
    reg [31:0] low_reg, high_reg, control_reg, offset_reg;
    reg [31:0] acquisition_reg, dc_reg;
    wire [223:0] data_out;
    wire valid_out, ready_out;
    wire [31:0] phase_out, frequency_out;
    wire [31:0] acquisition_out, fft_out;
    reg [31:0] tracking_reg, monitor_reg;
    reg monitor_ready_reg;
    wire [127:0] monitor_data_out;
    wire monitor_valid_out, monitor_last_out, monitor_reset_out;
    wire [31:0] tracking_status_out, monitor_status_out;
    always @(posedge clk) begin
        reset_reg <= rst_n;
        data_reg <= adc_data;
        valid_reg <= adc_valid;
        ready_reg <= dac_ready;
        low_reg <= frequency_low;
        high_reg <= frequency_high;
        control_reg <= control;
        offset_reg <= phase_offset;
        acquisition_reg <= acquisition_control; dc_reg <= test_dc;
        tracking_reg<=tracking_control; monitor_reg<=monitor_control; monitor_ready_reg<=monitor_ready;
        monitor_data<=monitor_data_out; monitor_valid<=monitor_valid_out; monitor_last<=monitor_last_out;
        monitor_reset<=monitor_reset_out; tracking_status<=tracking_status_out; monitor_status<=monitor_status_out;
        dac_data <= data_out;
        dac_valid <= valid_out;
        adc_ready <= ready_out;
        phase_status <= phase_out;
        frequency_status <= frequency_out;
        acquisition_status <= acquisition_out; fft_status <= fft_out;
    end
    laser_pll detector (.clk(clk), .rst_n(reset_reg), .s_axis_tdata(data_reg),
        .s_axis_tvalid(valid_reg), .s_axis_tready(ready_out), .m_axis_tdata(data_out),
        .m_axis_tvalid(valid_out), .m_axis_tready(ready_reg), .frequency_low(low_reg),
        .frequency_high(high_reg), .control(control_reg), .phase_offset(offset_reg),
        .acquisition_control(acquisition_reg), .test_dc(dc_reg),
        .tracking_control(tracking_reg), .monitor_control(monitor_reg),
        .tracking_status(tracking_status_out), .monitor_status(monitor_status_out),
        .m_monitor_tdata(monitor_data_out), .m_monitor_tvalid(monitor_valid_out),
        .m_monitor_tready(monitor_ready_reg), .m_monitor_tlast(monitor_last_out),
        .monitor_fifo_rst_n(monitor_reset_out),
        .phase_status(phase_out), .frequency_status(frequency_out),
        .acquisition_status(acquisition_out), .fft_status(fft_out));
endmodule
