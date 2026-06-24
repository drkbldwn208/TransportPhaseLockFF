`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06/22/2026 02:43:09 PM
// Design Name: 
// Module Name: iq_split
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


module iq_split #(
    parameter DATA_WIDTH = 16
    )(
    input wire clk,
    
    input wire [127:0] s_axis_tdata,
    input wire s_axis_tvalid,
    
    output wire [63:0] m_axis_i_tdata,
    output wire m_axis_i_tvalid,
    
    output wire [63:0] m_axis_q_tdata,
    output wire m_axis_q_tvalid,
    
    output wire [63:0] adc_bus
    );
    
    genvar i;
    
    generate
        for (i = 0; i < 4; i = i + 1) begin 
            assign m_axis_i_tdata[i*DATA_WIDTH +: DATA_WIDTH] = s_axis_tdata[2*i*DATA_WIDTH +: DATA_WIDTH];
            assign adc_bus[i*DATA_WIDTH +: DATA_WIDTH] = s_axis_tdata[2*i*DATA_WIDTH +: DATA_WIDTH];
            assign m_axis_q_tdata[i*DATA_WIDTH +: DATA_WIDTH] = s_axis_tdata[((2*i)+1)*DATA_WIDTH +: DATA_WIDTH];
        end
    endgenerate 
        
    assign m_axis_i_tvalid = s_axis_tvalid;
    assign m_axis_q_tvalid = s_axis_tvalid;


endmodule

