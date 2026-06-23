`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 05/19/2026 03:05:36 PM
// Design Name: 
// Module Name: axis_power_mod
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


module sync_axis_power_mod(
    input wire clk,
    input wire rst_n,
    input wire [15:0] sync_in, 
    input wire open_loop_toggle,
    input wire [15:0] open_loop_setpoint,
    output wire [223:0] m_axis_tdata,
    output wire m_axis_tvalid
    );
    
        
    assign m_axis_tdata = open_loop_toggle ? {7{{16'b0, open_loop_setpoint[15:0]}}} : {7{{16'b0, sync_in[15:0]}}};
    assign m_axis_tvalid = 1'b1;
    
endmodule
    