`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 04/27/2026 07:22:15 PM
// Design Name: 
// Module Name: ErrorSignal_Wrapper
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


module ErrorSignal_Wrapper #(
    parameter IN_WIDTH = 12,
    parameter OUT_WIDTH = 20,
    parameter WRAP_THRESHOLD = 384
)(
    input wire clk,
    input wire rst_n,
    input wire [IN_WIDTH*8-1:0] phase_1_in,
    input wire [IN_WIDTH*8-1:0] phase_2_in,
    input wire unwrap_en,
    input wire [OUT_WIDTH*8-1:0] perturb_in_tdata,
    input wire perturb_in_tvalid,
    output wire perturb_in_tready,
    output wire [OUT_WIDTH*8-1:0] error_signal_out,
    output wire [OUT_WIDTH*8-1:0] raw_error_out_tdata,
    output wire raw_error_out_tvalid,
    input wire raw_error_out_tready,
    output wire [OUT_WIDTH*8-1:0] summed_error_out_tdata,
    output wire summed_error_out_tvalid,
    input wire summed_error_out_tready
);

wire [OUT_WIDTH*8-1:0] raw_error_out;

PhaseUnwrapper_8Lane #(
    .IN_WIDTH(IN_WIDTH),
    .OUT_WIDTH(OUT_WIDTH),
    .WRAP_THRESHOLD(WRAP_THRESHOLD)
)(
    .clk(clk),
    .rst_n(rst_n),
    .phase_1_in(phase_1_in),
    .phase_2_in(phase_2_in),
    .unwrap_en(unwrap_en),
    .error_signal_out(raw_error_out)
);

genvar i;
generate  
    for (i = 0; i < 8; i = i+1) begin
        assign error_signal_out[i*OUT_WIDTH +: OUT_WIDTH] = raw_error_out[i*OUT_WIDTH +: OUT_WIDTH] + perturb_in_tdata[i*OUT_WIDTH +: OUT_WIDTH];
        assign raw_error_out_tdata[i*OUT_WIDTH +: OUT_WIDTH] = raw_error_out[i*OUT_WIDTH +: OUT_WIDTH];
        assign summed_error_out_tdata[i*OUT_WIDTH +: OUT_WIDTH] = raw_error_out[i*OUT_WIDTH +: OUT_WIDTH] + perturb_in_tdata[i*OUT_WIDTH +: OUT_WIDTH];
    end
endgenerate 

assign perturb_in_tready = 1'b1;
assign raw_error_out_tvalid = 1'b1;
assign summed_error_out_tvalid = 1'b1;

endmodule
