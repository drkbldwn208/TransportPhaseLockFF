`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/03/2026 03:31:53 PM
// Design Name: 
// Module Name: PIController_8Lane
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


module PIController_8Lane #(
  parameter int CONTROL_WIDTH = 32,
  parameter int ERROR_WIDTH = 20,
  parameter int KP_WIDTH = 16,
  parameter int KI_WIDTH = 16
)(
  input logic clk,
  input logic rst_n,
  input logic signed [ERROR_WIDTH*8 - 1:0] error_in,
  input logic signed [KP_WIDTH-1:0] kp_in,
  input logic signed [KI_WIDTH-1:0] ki_in,
  input logic unsigned [4:0] kp_bit_shift_right,
  input logic unsigned [4:0] ki_bit_shift_right,
  output logic signed [CONTROL_WIDTH*8 - 1:0] control_out,
  input integrator_gpio_rst
);

  //Internal registers
  logic signed [CONTROL_WIDTH*8 - 1:0] pi_output_reg;
  //P delay registers
  logic signed [ERROR_WIDTH-1:0] error_in_reg [7:0];
  logic signed [ERROR_WIDTH-1:0] error_in_dly [7:0];
  logic signed [ERROR_WIDTH-1:0] error_in_dly2 [7:0];
  logic signed [ERROR_WIDTH-1:0] error_in_dly3 [7:0];
  logic signed [ERROR_WIDTH-1:0] error_in_dly4 [7:0];
  logic signed [ERROR_WIDTH + KP_WIDTH:0] p_products [7:0];
  logic signed [ERROR_WIDTH + KP_WIDTH:0] p_products_shifted [7:0];

  //Integrator pairwise sum registers. Have to pipeline in 3 stages to avoid long combinational paths.
  logic signed [ERROR_WIDTH:0] s1 [7:0];
  logic signed [ERROR_WIDTH+1:0] s2 [7:0];
  logic signed [ERROR_WIDTH+2:0] s3 [7:0];
  logic signed [ERROR_WIDTH + 3 + KI_WIDTH:0] i_products [7:0];
  logic signed [ERROR_WIDTH + 3 + KI_WIDTH:0] integrator_out [7:0];
  logic signed [ERROR_WIDTH + 3 + KI_WIDTH:0] integrator_out_shifted [7:0];

  //Global accumulator register
  logic signed [ERROR_WIDTH + 3 + KI_WIDTH:0] global_accumulator;



  //Bit shift registers controlled by GPIO
  logic unsigned [4:0] kp_bit_shift_right_reg;
  logic unsigned [4:0] ki_bit_shift_right_reg;

  //KI and KP registers
  logic signed [KI_WIDTH-1:0] ki_reg;
  logic signed [KP_WIDTH-1:0] kp_reg;

  always_ff @(posedge clk) begin
    if(!rst_n) begin
      for(int i = 0; i < 8; i++) begin
        //P registers
        error_in_reg[i] <= '0;
        error_in_dly[i] <= '0;
        error_in_dly2[i] <= '0;
        error_in_dly3[i] <= '0;
        error_in_dly4[i] <= '0;
        p_products[i] <= '0;
        p_products_shifted[i] <= '0;
        //I registers
        s1[i] <= '0;
        s2[i] <= '0;
        s3[i] <= '0;
        i_products[i] <= '0;
        integrator_out[i] <= '0;
        integrator_out_shifted[i] <= '0;
        //PI output registers
        pi_output_reg[i*CONTROL_WIDTH +: CONTROL_WIDTH] <= '0;
      end
      //Global accumulator register
      global_accumulator <= '0;
      //Bit shift registers and KI and KP registers
      kp_bit_shift_right_reg <= '0;
      ki_bit_shift_right_reg <= '0;
      ki_reg <= '0;
      kp_reg <= '0;
    end else if (integrator_gpio_rst) begin
        global_accumulator <= '0;

    end else begin
      //Delay error signals for next clock cycle
      for (int i = 0; i < 8; i++) begin
        error_in_reg[i] <= error_in[i*ERROR_WIDTH +: ERROR_WIDTH];
      end
      //Update bit shift registers and KI and KP registers
      kp_bit_shift_right_reg <= kp_bit_shift_right;
      ki_bit_shift_right_reg <= ki_bit_shift_right;
      ki_reg <= ki_in;
      kp_reg <= kp_in;



      //Calculate pairwise sums
      s1[0] <= error_in_reg[0];
      s1[1] <= error_in_reg[0] + error_in_reg[1];

      s1[2] <= error_in_reg[2];
      s1[3] <= error_in_reg[2] + error_in_reg[3];

      s1[4] <= error_in_reg[4];
      s1[5] <= error_in_reg[4] + error_in_reg[5];

      s1[6] <= error_in_reg[6];
      s1[7] <= error_in_reg[6] + error_in_reg[7];

      //Delay error signals for next clock cycle
      for (int i = 0; i < 8; i++) begin
        error_in_dly[i] <= error_in_reg[i];
      end



      //Stage 2 sums
      s2[0] <= s1[0];
      s2[1] <= s1[1];

      s2[2] <= s1[1] + s1[2];
      s2[3] <= s1[1] + s1[3];

      s2[4] <= s1[4];
      s2[5] <= s1[5];

      s2[6] <= s1[5] + s1[6];
      s2[7] <= s1[5] + s1[7];



      for (int i = 0; i < 8; i++) begin
        error_in_dly2[i] <= error_in_dly[i];
      end

      //Stage 3 sums
      s3[0] <= s2[0];
      s3[1] <= s2[1];
      s3[2] <= s2[2];
      s3[3] <= s2[3];
      s3[4] <= s2[3] + s2[4];
      s3[5] <= s2[3] + s2[5];
      s3[6] <= s2[3] + s2[6];
      s3[7] <= s2[3] + s2[7];

      for (int i = 0; i < 8; i++) begin
        error_in_dly3[i] <= error_in_dly2[i];
      end

      for(int i = 0; i < 8; i++) begin
        i_products[i] <= $signed(s3[i]) * $signed(ki_reg);
        error_in_dly4[i] <= error_in_dly3[i];
      end

      global_accumulator <= global_accumulator + i_products[7];


      for(int i = 0; i < 8; i++) begin
        integrator_out[i] <= global_accumulator + i_products[i];

        p_products[i] <= $signed(error_in_dly4[i]) * $signed(kp_reg);
      end

      for(int i = 0; i < 8; i++) begin
        p_products_shifted[i] <= p_products[i] >>> kp_bit_shift_right_reg;
        integrator_out_shifted[i] <= integrator_out[i] >>> ki_bit_shift_right_reg;
      end


      for(int i = 0; i < 8; i++) begin
        pi_output_reg[i*CONTROL_WIDTH +: CONTROL_WIDTH] <= p_products_shifted[i] + integrator_out_shifted[i];
      end
    end
  end

  assign control_out = pi_output_reg;

endmodule
