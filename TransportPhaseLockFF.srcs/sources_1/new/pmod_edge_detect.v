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
)(
    input wire clk,
    input wire rst_n,
    input wire pmod_in,
    
    output wire sync_edge
    );
    
    (* ASYNC_REG = "TRUE" *) reg sync_0;
    (* ASYNC_REG = "TRUE" *) reg sync_1;
    
    reg sync_last;
    
    
    always @(posedge clk) begin
        if (!rst_n) begin
            sync_0 <= 1'b0;
            sync_1 <= 1'b0;
            sync_last <= 1'b0;
        end else begin 
            sync_0 <= pmod_in;
            sync_1 <= sync_0;
            sync_last <= sync_1;
        end
    end
    
    assign sync_edge = sync_1 & ~sync_last;

endmodule
