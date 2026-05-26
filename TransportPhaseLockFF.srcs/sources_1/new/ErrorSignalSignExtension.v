`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/17/2026 12:23:49 PM
// Design Name: 
// Module Name: ErrorSignalSignExtension
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


module ErrorSignalSignExtension(
    input wire clk,

    input wire [95:0] s_axis_tdata,
    input wire s_axis_tvalid,
    output wire s_axis_tready,
    
    output wire [127:0] m_axis_tdata,
    output wire m_axis_tvalid,
    input wire m_axis_tready
    );
    
    assign m_axis_tvalid = s_axis_tvalid;
    assign s_axis_tready = m_axis_tready;
    
    
    genvar i;
    generate
        for (i=0; i<8; i = i+1) begin
            wire [11:0] chan_data = s_axis_tdata[(i*12) + 11 : i*12];
            
            assign m_axis_tdata[(i*16) + 15: i*16] = { {4{chan_data[11]}}, chan_data };
            
        end
    endgenerate
    
endmodule
