`timescale 1ns / 1ps
// Vivado 2024.1 block-design module references require a Verilog top file.
module laser_pll_wrapper (
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axis:m_axis:m_monitor, ASSOCIATED_RESET rst_n:monitor_fifo_rst_n" *)
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
    input wire [31:0] acquisition_control,
    input wire [31:0] test_dc,
    input wire [31:0] tracking_control,
    input wire [31:0] monitor_control,
    output wire [31:0] tracking_status,
    output wire [31:0] monitor_status,
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *) output wire monitor_fifo_rst_n,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_monitor TDATA" *) output wire [127:0] m_monitor_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_monitor TVALID" *) output wire m_monitor_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_monitor TREADY" *) input wire m_monitor_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_monitor TLAST" *) output wire m_monitor_tlast,
    output wire [31:0] phase_status,
    output wire [31:0] frequency_status,
    output wire [31:0] acquisition_status,
    output wire [31:0] fft_status
);
    laser_pll detector (
        .clk(clk), .rst_n(rst_n), .s_axis_tdata(s_axis_tdata),
        .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
        .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready), .frequency_low(frequency_low),
        .frequency_high(frequency_high), .control(control), .phase_offset(phase_offset),
        .acquisition_control(acquisition_control), .test_dc(test_dc),
        .tracking_control(tracking_control), .monitor_control(monitor_control),
        .tracking_status(tracking_status), .monitor_status(monitor_status),
        .monitor_fifo_rst_n(monitor_fifo_rst_n), .m_monitor_tdata(m_monitor_tdata),
        .m_monitor_tvalid(m_monitor_tvalid), .m_monitor_tready(m_monitor_tready),
        .m_monitor_tlast(m_monitor_tlast),
        .phase_status(phase_status), .frequency_status(frequency_status),
        .acquisition_status(acquisition_status), .fft_status(fft_status)
    );
endmodule
