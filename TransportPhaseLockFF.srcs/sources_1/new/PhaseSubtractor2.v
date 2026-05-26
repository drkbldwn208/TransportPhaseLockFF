`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/05/2026 11:12:30 AM
// Design Name: 
// Module Name: PhaseSubtractor2
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


module PhaseSubtractor2 #(
    parameter PHASE_WIDTH = 12
    )(
    input wire clk,
    input wire rst_n,
    input wire signed [PHASE_WIDTH*8-1:0] phase_1_in,
    input wire signed [PHASE_WIDTH*8-1:0] phase_2_in,
    input wire loop_en,
    output wire signed [PHASE_WIDTH*8-1:0] error_signal_out
    );
    
    reg signed [PHASE_WIDTH-1:0] phase_1_in_reg [7:0];
    reg signed [PHASE_WIDTH-1:0] phase_2_in_reg [7:0];
    reg signed [PHASE_WIDTH*8-1:0] error_signal_out_reg;
    
    integer i,j;
    
    reg signed [PHASE_WIDTH-1:0] ref_doubled;
    reg signed [PHASE_WIDTH:0] raw_diff;
    
    always @(posedge clk) begin
        if (!rst_n) begin
            error_signal_out_reg <= 0;
            for (i = 0; i < 8; i = i + 1) begin
                phase_1_in_reg[i] <= 0;
                phase_2_in_reg[i] <= 0;
            end 
        end else begin
            for (j = 0; j < 8; j = j + 1) begin
                phase_1_in_reg[j] <= phase_1_in[j*PHASE_WIDTH +: PHASE_WIDTH];
                phase_2_in_reg[j] <= phase_2_in[j*PHASE_WIDTH +: PHASE_WIDTH];
                //Double and wrap reference phase
                //Bit shift left by 1, sign-extend from the new Pi (=512) boundary sign bit
                ref_doubled = { {3{phase_1_in_reg[j][8]}}, phase_1_in_reg[j][7:0], 1'b0};
                
                raw_diff = ref_doubled - phase_2_in_reg[j];
                if (loop_en) begin
                    if (raw_diff > 13'sd512) begin
                        error_signal_out_reg[j*PHASE_WIDTH +: PHASE_WIDTH] <= raw_diff - 13'sd1024;
                    end else if (raw_diff < -13'sd512) begin
                        error_signal_out_reg[j*PHASE_WIDTH +: PHASE_WIDTH] <= raw_diff + 13'sd1024;
                    end else begin
                        error_signal_out_reg[j*PHASE_WIDTH +: PHASE_WIDTH] <= raw_diff;
                    end
                end else begin
                    error_signal_out_reg[j*PHASE_WIDTH +: PHASE_WIDTH] <= 0;
                end
            end
        end
    end
 
    assign error_signal_out = error_signal_out_reg;   
    
endmodule