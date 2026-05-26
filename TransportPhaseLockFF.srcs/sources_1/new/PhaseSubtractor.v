`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/03/2026 03:03:03 PM
// Design Name: 
// Module Name: PhaseSubtractor
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


module PhaseSubtractor #(
    parameter PHASE_WIDTH = 12
    )(
    input clk,
    input rst_n,
    input [PHASE_WIDTH*8-1:0] phase_1_in,
    input [PHASE_WIDTH*8-1:0] phase_2_in,
    output [PHASE_WIDTH*8-1:0] error_signal_out
    );
    
    reg signed [PHASE_WIDTH-1:0] phase_1_in_reg [7:0];
    reg signed [PHASE_WIDTH-1:0] phase_2_in_reg [7:0];
    reg signed [8*PHASE_WIDTH - 1:0] error_signal_out_reg;
    
    
    integer i;
    integer j;
    
    
    localparam signed [PHASE_WIDTH - 1:0] ERROR_MAX = {1'b0, {(PHASE_WIDTH-1){1'b1}}};
    localparam signed [PHASE_WIDTH - 1:0] ERROR_MIN = {1'b1, {(PHASE_WIDTH-1){1'b0}}};
    always @(posedge clk) begin
        if (!rst_n) begin
            error_signal_out_reg <= 0;
            for (i = 0; i < 8; i =  i + 1) begin
                phase_1_in_reg[i] <= 0;
                phase_2_in_reg[i] <= 0;
            end
        end else begin
            for (j = 0; j < 8; j =  j + 1) begin  
                phase_1_in_reg[j] <= phase_1_in[j*PHASE_WIDTH +: PHASE_WIDTH];
                phase_2_in_reg[j] <= phase_2_in[j*PHASE_WIDTH +: PHASE_WIDTH];
                error_signal_out_reg[j*PHASE_WIDTH +: PHASE_WIDTH] <= (phase_1_in_reg[j] - phase_2_in_reg[j]);
            end
        end
    end
    
    assign error_signal_out = error_signal_out_reg;
            
endmodule
