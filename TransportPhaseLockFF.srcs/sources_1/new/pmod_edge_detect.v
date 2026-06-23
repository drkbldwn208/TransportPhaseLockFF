`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 05/26/2026 11:55:54 AM
// Design Name: 
// Module Name: pmod_edge_detect
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


module pmod_sync_edge #(
    parameter FILTER_CYCLES = 5
)(
    input wire clk,
    input wire rst_n,
    input wire pmod_in,
    
    output reg clean_out,
    output wire edge_pos,
    output wire edge_neg
    );
    
    localparam COUNT_WIDTH = $clog2(FILTER_CYCLES + 1);
    reg [COUNT_WIDTH - 1:0] counter;
    
    reg sync_0;
    reg sync_1;
    
    always @(posedge clk) begin
        if (!rst_n) begin
            sync_0 <= 1'b0;
            sync_1 <= 1'b0;
        end else begin 
            sync_0 <= pmod_in;
            sync_1 <= sync_0;
        end
    end
    
    
    always @(posedge clk) begin
        if (!rst_n) begin 
            clean_out <= 1'b0;
            counter <= 0;
        end else begin 
            if (sync_1 == clean_out) begin
                counter <= 0;
            end else begin 
                if (counter < FILTER_CYCLES) begin
                    counter <= counter + 1;
                end else begin 
                    clean_out <= sync_1;
                    counter <= 0;
                end
            end
        end
    end
     
endmodule
