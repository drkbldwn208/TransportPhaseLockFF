`timescale 1ns / 1ps
// Vivado 2024.1 block-design module references require a Verilog top file.
module laser_pll_wrapper (
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
    laser_pll detector (
        .clk(clk), .rst_n(rst_n), .s_axis_tdata(s_axis_tdata),
        .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
        .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready), .frequency_low(frequency_low),
        .frequency_high(frequency_high), .control(control), .phase_offset(phase_offset),
        .phase_status(phase_status), .frequency_status(frequency_status)
    );
endmodule
