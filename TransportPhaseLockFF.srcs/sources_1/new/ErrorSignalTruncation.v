`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 04/28/2026 12:51:48 PM
// Design Name: 
// Module Name: ErrorSignalTruncation
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


module ErrorSignalTruncation(
    input wire clk,

    input wire [159:0] s_axis_tdata,  // 8 channels * 20 bits = 160 bits
    input wire s_axis_tvalid,
    output wire s_axis_tready,

    output wire [127:0] m_axis_tdata, // 8 channels * 16 bits = 128 bits
    output wire m_axis_tvalid,
    input wire m_axis_tready
    );

    assign m_axis_tvalid = s_axis_tvalid;
    //assign s_axis_tready = m_axis_tready;
    assign s_axis_tready = 1'b1;
    
    genvar i;
    generate
        for (i=0; i<8; i = i+1) begin
            // Extract the 20-bit channel
            wire [19:0] chan_data = s_axis_tdata[(i*20) + 19 : i*20];

            // Keep the sign bit (19), drop bits [18:15], keep lower 15 bits [14:0]
            assign m_axis_tdata[(i*16) + 15: i*16] = { chan_data[19], chan_data[14:0] };

        end
    endgenerate

endmodule