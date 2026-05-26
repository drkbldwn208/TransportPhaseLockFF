`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/04/2026 10:27:44 AM
// Design Name: 
// Module Name: NCO_Wrapper
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


module NCO_Wrapper #(
    PHASE_WIDTH = 32,
    OUT_WIDTH = 16
    )(
    input clk,
    input rst_n,
    input [PHASE_WIDTH*8 - 1:0] phase_in,
    output [OUT_WIDTH*8 - 1:0] m_axis_tdata,
    output m_axis_tvalid
    );
    
    NCO #(
    .PHASE_WIDTH(32),
    .ADDR_WIDTH(14),
    .AMP_WIDTH(16),
    .OUT_WIDTH(16)
    ) NCO_inst (
    .clk(clk),
    .rst_n(rst_n),
    .phase_in(phase_in),
    .nco_out(m_axis_tdata)
    );
    
    assign m_axis_tvalid = 1'b1;

endmodule
