`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06/26/2026 11:52:55 AM
// Design Name: 
// Module Name: gpio_pmod_trigger
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


module gpio_pmod_trigger(
    input wire clk,
    input wire [15:0] gpio_in,
    output reg pmod_driver_out
    );
    
    always @(posedge clk) begin
        pmod_driver_out <= (gpio_in == 0) ? 1'b1 : 1'b0; 
    end 
endmodule
