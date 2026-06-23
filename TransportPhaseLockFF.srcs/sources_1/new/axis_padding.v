`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06/22/2026 03:47:55 PM
// Design Name: 
// Module Name: axis_padding
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


module axis_padding #(
    parameter NUM_BYTES_IN = 11,
    parameter NUM_BYTES_OUT = 16
    )(
    input wire clk,
    
    input wire [NUM_BYTES_IN*8 - 1:0] s_axis_tdata,
    input wire s_axis_tvalid,
    
    output wire [NUM_BYTES_OUT*8 - 1:0] m_axis_tdata,
    output wire m_axis_tvalid
    );
    
    assign m_axis_tdata = {{(8*(NUM_BYTES_OUT - NUM_BYTES_IN)){s_axis_tdata[8*NUM_BYTES_IN - 1]}}, s_axis_tdata};
    assign m_axis_tvalid = s_axis_tvalid;
        
endmodule
