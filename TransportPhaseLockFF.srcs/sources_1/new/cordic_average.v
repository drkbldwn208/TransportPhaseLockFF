`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06/22/2026 03:07:55 PM
// Design Name: 
// Module Name: cordic_average
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


module cordic_average #(
    parameter DATA_WIDTH = 16
    )(
    input wire clk,
    input wire rst_n,
    
    input wire [63:0] s_axis_i_tdata,
    input wire s_axis_i_tvalid,
    
    input wire [63:0] s_axis_q_tdata,
    input wire s_axis_q_tvalid,
    
    output reg [31:0] m_axis_cartesian_tdata,
    output reg m_axis_cartesian_tvalid
    );
    
    
    wire signed [16:0] i0 = {s_axis_i_tdata[15], s_axis_i_tdata[15:0]};
    wire signed [16:0] i1 = {s_axis_i_tdata[31], s_axis_i_tdata[31:16]};
    wire signed [16:0] i2 = {s_axis_i_tdata[47], s_axis_i_tdata[47:32]};
    wire signed [16:0] i3 = {s_axis_i_tdata[63], s_axis_i_tdata[63:48]};
       
    wire signed [16:0] q0 = {s_axis_q_tdata[15], s_axis_q_tdata[15:0]};
    wire signed [16:0] q1 = {s_axis_q_tdata[31], s_axis_q_tdata[31:16]};
    wire signed [16:0] q2 = {s_axis_q_tdata[47], s_axis_q_tdata[47:32]};
    wire signed [16:0] q3 = {s_axis_q_tdata[63], s_axis_q_tdata[63:48]};
      
    wire signed [17:0] sum_i = i0 + i1 + i2 + i3;
    wire signed [17:0] sum_q = q0 + q1 + q2 + q3;
    
    wire signed [15:0] avg_i = sum_i >>> 3;
    wire signed [15:0] avg_q = sum_q >>> 3;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            m_axis_cartesian_tdata <= 32'b0;
            m_axis_cartesian_tvalid <= 1'b0;
        end else begin 
             m_axis_cartesian_tdata <= {avg_q, avg_i};
             m_axis_cartesian_tvalid <= 1'b1;
        end
    end 
endmodule
