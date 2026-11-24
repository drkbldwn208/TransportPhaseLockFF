`timescale 1ns / 1ps
module pdh_tones_wrapper (
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF m_sum:m_ref, ASSOCIATED_RESET rst_n" *) input wire clk,
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *) input wire rst_n,
    input wire gpio_clk,
    input wire [31:0] control, amplitudes, reference_settings,
    input wire [31:0] carrier_fcw_low, carrier_fcw_high, modulation_fcw_low, modulation_fcw_high,
    output wire [31:0] status, feature_version,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_sum TDATA" *) output wire [223:0] m_sum_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_sum TVALID" *) output wire m_sum_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_sum TREADY" *) input wire m_sum_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_ref TDATA" *) output wire [127:0] m_ref_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_ref TVALID" *) output wire m_ref_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_ref TREADY" *) input wire m_ref_tready
);
    pdh_tones source (.clk(clk),.rst_n(rst_n),.control(control),.amplitudes(amplitudes),
        .gpio_clk(gpio_clk),.reference_settings(reference_settings),
        .carrier_fcw_low(carrier_fcw_low),.carrier_fcw_high(carrier_fcw_high),
        .modulation_fcw_low(modulation_fcw_low),.modulation_fcw_high(modulation_fcw_high),.status(status),.feature_version(feature_version),
        .m_sum_tdata(m_sum_tdata),.m_sum_tvalid(m_sum_tvalid),.m_sum_tready(m_sum_tready),
        .m_ref_tdata(m_ref_tdata),.m_ref_tvalid(m_ref_tvalid),.m_ref_tready(m_ref_tready));
endmodule
