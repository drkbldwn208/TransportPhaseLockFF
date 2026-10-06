// Timing-only source/sink registers model synchronous RFDC/GPIO boundaries.
// These registers are NOT part of the PLL or its quoted pipeline latency.
module laser_pll_timing_top (
    input wire clk,
    input wire rst_n,
    input wire [127:0] adc_data,
    input wire adc_valid,
    input wire dac_ready,
    input wire [31:0] frequency_low, frequency_high, control, phase_offset,
    output reg [223:0] dac_data,
    output reg dac_valid, adc_ready,
    output reg [31:0] phase_status, frequency_status
);
    reg reset_reg, valid_reg, ready_reg;
    reg [127:0] data_reg;
    reg [31:0] low_reg, high_reg, control_reg, offset_reg;
    wire [223:0] data_out;
    wire valid_out, ready_out;
    wire [31:0] phase_out, frequency_out;
    always @(posedge clk) begin
        reset_reg <= rst_n;
        data_reg <= adc_data;
        valid_reg <= adc_valid;
        ready_reg <= dac_ready;
        low_reg <= frequency_low;
        high_reg <= frequency_high;
        control_reg <= control;
        offset_reg <= phase_offset;
        dac_data <= data_out;
        dac_valid <= valid_out;
        adc_ready <= ready_out;
        phase_status <= phase_out;
        frequency_status <= frequency_out;
    end
    laser_pll detector (.clk(clk), .rst_n(reset_reg), .s_axis_tdata(data_reg),
        .s_axis_tvalid(valid_reg), .s_axis_tready(ready_out), .m_axis_tdata(data_out),
        .m_axis_tvalid(valid_out), .m_axis_tready(ready_reg), .frequency_low(low_reg),
        .frequency_high(high_reg), .control(control_reg), .phase_offset(offset_reg),
        .phase_status(phase_out), .frequency_status(frequency_out));
endmodule
