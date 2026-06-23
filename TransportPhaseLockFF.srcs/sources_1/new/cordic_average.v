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
    
    reg [16:0] sum_0_i, sum_1_i;
    reg [16:0] sum_0_q, sum_1_q;
    reg [18:0] sum_f_i, sum_f_q;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sum_0_i <= 17'b0;
            sum_0_q <= 17'b0;
            sum_1_i <= 17'b0;
            sum_1_q <= 17'b0;
            sum_f_i <= 19'b0;
            sum_f_q <= 19'b0;
            m_axis_cartesian_tdata <= 32'b0;
            m_axis_cartesian_tvalid <= 1'b0;
        end else begin 
             sum_0_i <= s_axis_i_tdata[15:0] + s_axis_i_tdata[31:16];
             sum_0_q <= s_axis_q_tdata[15:0] + s_axis_q_tdata[31:16];
             sum_1_i <= s_axis_i_tdata[47:32] + s_axis_i_tdata[63:48];
             sum_1_q <= s_axis_q_tdata[47:32] + s_axis_q_tdata[63:48];
             sum_f_i <= (sum_0_i + sum_1_i) >>> 4;
             sum_f_q <= (sum_0_q + sum_1_q) >>> 4;
             m_axis_cartesian_tdata <= {sum_f_q[15:0], sum_f_i[15:0]};
             m_axis_cartesian_tvalid <= 1'b1;
        end
    end 
endmodule
