`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06/23/2026 03:04:28 PM
// Design Name: 
// Module Name: PostCordicExtension
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


module PostCordicExtension(
    input wire clk,
    
    input wire [31:0] s_axis_tdata,
    input wire s_axis_tvalid,
    
    output wire [127:0] m_axis_tdata,
    output wire m_axis_tvalid
    );

    assign m_axis_tvalid = 1'b1;
    assign m_axis_tdata = {4{s_axis_tdata[31:0]}};

endmodule
