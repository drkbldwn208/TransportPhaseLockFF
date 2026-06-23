`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06/22/2026 02:04:39 PM
// Design Name: 
// Module Name: async_fifo_latch
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


module async_fifo_latch(
    input wire clk,
    input wire rst_n,
    input wire [31:0] s_axis_tdata,
    input wire s_axis_tvalid,
    output wire s_axis_tready,
    
    output reg [15:0] m_axis_tdata,
    output reg m_axis_tvalid
    );
    
    assign s_axis_tready = 1'b1;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            m_axis_tdata <= 32'b0;
            m_axis_tvalid <= 1'b0;
        end else begin 
            m_axis_tvalid <= 1'b1;
            if (s_axis_tvalid) begin 
                m_axis_tdata[15:0] <= s_axis_tdata[15:0];
            end
        end
    end 
        
endmodule
