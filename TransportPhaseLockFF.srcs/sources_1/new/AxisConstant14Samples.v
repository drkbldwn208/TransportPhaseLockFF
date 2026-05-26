`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/13/2026 02:47:18 PM
// Design Name: 
// Module Name: AxisConstant14Samples
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


module AxisConstant14Samples(
    input wire aclk,
    
    output wire [223:0] m_axis_tdata,
    output wire m_axis_tvalid
    );
    
    assign m_axis_tdata = 224'h0000_7FFF_0000_7FFF_0000_7FFF_0000_7FFF_0000_7FFF_0000_7FFF_0000_7FFF;
    assign m_axis_tvalid = 1'b1;
    
endmodule
