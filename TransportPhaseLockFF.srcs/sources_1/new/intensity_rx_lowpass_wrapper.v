`timescale 1ns / 1ps
// Plain Verilog boundary for Vivado block-design module-reference inference.
module intensity_rx_lowpass_wrapper (
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_RESET rst_n" *) input wire clk,
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *) input wire rst_n,
    input wire [63:0] i_data, q_data,
    input wire sample_valid,
    output wire [63:0] filtered_i, filtered_q,
    output wire filtered_valid
);
    intensity_rx_lowpass filter (.clk(clk), .rst_n(rst_n), .i_data(i_data),
        .q_data(q_data), .sample_valid(sample_valid), .filtered_i(filtered_i),
        .filtered_q(filtered_q), .filtered_valid(filtered_valid));
endmodule
