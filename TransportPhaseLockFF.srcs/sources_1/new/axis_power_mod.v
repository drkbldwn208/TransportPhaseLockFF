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


module axis_power_mod(
    input wire clk,
    input wire rst_n,
    input wire [15:0] async_in, 
    output wire [127:0] m_axis_tdata,
    output wire m_axis_tvalid
    );
    // latch gpio value
    reg [15:0] latch_r1, latch_r2, latch_r3;
    reg [15:0] latched_data;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin 
            latch_r1 <= 32'h7FFF;
            latch_r2 <= 32'h7FFF;
            latch_r3 <= 32'h7FFF;
            latched_data <= 32'h7FFF;
        end else begin 
            latch_r1 <= async_in;
            latch_r2 <= latch_r1;
            latch_r3 <= latch_r2;
            if ((latch_r1 == latch_r2) && (latch_r2 == latch_r3)) begin
                latched_data <= latch_r3;
            end
        end
    end
        
    assign m_axis_tdata = {4{{16'b0, latched_data}}};
    assign m_axis_tvalid = 1'b1;
endmodule
    