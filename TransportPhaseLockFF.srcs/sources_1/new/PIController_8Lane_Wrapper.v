`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/03/2026 03:34:45 PM
// Design Name: 
// Module Name: PIController_8Lane_Wrapper
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


module PIController_Wrapper #(
    parameter CONTROL_WIDTH = 32,
    parameter ERROR_WIDTH = 20,
    parameter KP_WIDTH = 16,
    parameter KI_WIDTH = 16
    )(
    input wire clk,
    input wire rst_n,
    input wire [ERROR_WIDTH*8 - 1:0] error_signal_unfolded,
    input wire [KP_WIDTH - 1:0] kp_in,
    input wire [KI_WIDTH - 1:0] ki_in,
    input wire [4:0] kp_right_bit_shift_in,
    input wire [4:0] ki_right_bit_shift_in,
    output wire [CONTROL_WIDTH*8 - 1:0] control_output,
    input wire loop_en,
    input wire integrator_gpio_rst,
    output wire [CONTROL_WIDTH*8 - 1:0] control_out_tdata,
    output wire control_out_tvalid,
    input wire control_out_tready
    );
    
   wire [ERROR_WIDTH*8 - 1:0] error_in;
   assign error_in = loop_en ? error_signal_unfolded : 96'b0;
   assign control_out_tdata = control_output;
   assign control_out_tvalid = 1'b1;    

  PIController_8Lane #(
    .CONTROL_WIDTH(CONTROL_WIDTH),
    .ERROR_WIDTH(ERROR_WIDTH),
    .KP_WIDTH(KP_WIDTH),
    .KI_WIDTH(KI_WIDTH)
    ) PIControllerInst (
    .clk(clk),
    .rst_n(rst_n),
    .error_in(error_in),
    .kp_in(kp_in),
    .ki_in(ki_in),
    .kp_bit_shift_right(kp_right_bit_shift_in),
    .ki_bit_shift_right(ki_right_bit_shift_in),
    .control_out(control_output),
    .integrator_gpio_rst(integrator_gpio_rst)
  );
  
   
endmodule
