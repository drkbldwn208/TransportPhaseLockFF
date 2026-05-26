`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/03/2026 04:17:08 PM
// Design Name: 
// Module Name: PhaseAccumulator_Wrapper
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


module PhaseAccumulator_Wrapper #(
    parameter PHASE_WIDTH = 32
    )(
    input clk,
    input rst_n,
    input [PHASE_WIDTH-1:0] center_freq_word,
    input [PHASE_WIDTH*8-1:0] pi_control_in,
    
    input wire [PHASE_WIDTH*8-1:0] perturb_in_tdata,
    input wire perturb_in_tvalid,
    output wire perturb_in_tready,
    
    output [PHASE_WIDTH*8-1:0] phase_out
);

wire [PHASE_WIDTH*8-1:0] raw_phase_out;

    PhaseAccumulator_8Lane #(
    .PHASE_WIDTH(32)
    ) PhaseAccumulatorInst (
    .clk(clk),
    .rst_n(rst_n),
    .center_freq_word(center_freq_word),
    .pi_control_in(pi_control_in),
    .phase_out(raw_phase_out)
);

genvar i;
generate  
    for (i = 0; i < 8; i = i+1) begin
        assign phase_out[i*PHASE_WIDTH +: PHASE_WIDTH] = raw_phase_out[i*PHASE_WIDTH +: PHASE_WIDTH] + perturb_in_tdata[i*PHASE_WIDTH +: PHASE_WIDTH];
    end
endgenerate 

assign perturb_in_tready = 1'b1;
 
endmodule
