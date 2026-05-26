`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/03/2026 04:07:42 PM
// Design Name: 
// Module Name: PhaseAccumulator_8Lane
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


module PhaseAccumulator_8Lane #(
  parameter int PHASE_WIDTH = 32
)(
  input logic clk,
  input logic rst_n,

  input logic unsigned [PHASE_WIDTH-1:0] center_freq_word,

  input logic signed [PHASE_WIDTH*8-1:0] pi_control_in,

  output logic signed [PHASE_WIDTH*8-1:0] phase_out
);

  //Internal registers
  logic signed [PHASE_WIDTH-1:0] center_freq_word_reg;
  logic signed [PHASE_WIDTH-1:0] inc_s1 [7:0]; //Base increment
  logic signed [PHASE_WIDTH-1:0] s2[7:0]; //Sum of increments
  logic signed [PHASE_WIDTH-1:0] s3[7:0]; //Sum of increments
  logic signed [PHASE_WIDTH-1:0] s4[7:0]; //Sum of increments

  logic signed [PHASE_WIDTH-1:0] global_phase;
  logic signed [PHASE_WIDTH*8-1:0] phase_out_reg;

  always_ff @(posedge clk) begin
    if(!rst_n) begin
      for(int i = 0; i < 8; i++) begin
        inc_s1[i] <= '0;
        s2[i] <= '0;
        s3[i] <= '0;
        s4[i] <= '0;
      end
      phase_out_reg <= '0;
      center_freq_word_reg <= 32'd185685333;
      global_phase <= '0;
    end else begin
      center_freq_word_reg <= center_freq_word;
      //Calculate base increment
      for(int i = 0; i < 8; i++) begin
        inc_s1[i] <= center_freq_word_reg + pi_control_in[i*PHASE_WIDTH +: PHASE_WIDTH];
      end

      //Calculate pairwise sums
      s2[0] <= inc_s1[0];
      s2[1] <= inc_s1[0] + inc_s1[1];
      s2[2] <= inc_s1[2];
      s2[3] <= inc_s1[2] + inc_s1[3];
      s2[4] <= inc_s1[4];
      s2[5] <= inc_s1[4] + inc_s1[5];
      s2[6] <= inc_s1[6];
      s2[7] <= inc_s1[6] + inc_s1[7];



      //Calculate quad sums
      s3[0] <= s2[0];
      s3[1] <= s2[1];
      s3[2] <= s2[1] + s2[2];
      s3[3] <= s2[1] + s2[3];
      s3[4] <= s2[4];
      s3[5] <= s2[5];
      s3[6] <= s2[5] + s2[6];
      s3[7] <= s2[5] + s2[7];

      //Calculate oct sums
      s4[0] <= s3[0];
      s4[1] <= s3[1];
      s4[2] <= s3[2];
      s4[3] <= s3[3];
      s4[4] <= s3[3] + s3[4];
      s4[5] <= s3[3] + s3[5];
      s4[6] <= s3[3] + s3[6];
      s4[7] <= s3[3] + s3[7];

      global_phase <= global_phase + s4[7];

      for(int i = 0; i < 8; i++) begin
        phase_out_reg[PHASE_WIDTH*i +: PHASE_WIDTH] <= global_phase + s4[i];
      end

    end
  end

  assign phase_out = phase_out_reg;

endmodule

