`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/05/2026 11:27:41 AM
// Design Name: 
// Module Name: AXISConstant
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

module AXISConstant(
    input wire aclk,
    
    output wire [127:0] m_axis_tdata,
    output wire m_axis_tvalid
    );
    
    assign m_axis_tdata = 128'h0000_7FFF_0000_7FFF_0000_7FFF_0000_7FFF;
    assign m_axis_tvalid = 1'b1;
    
    
    
endmodule
