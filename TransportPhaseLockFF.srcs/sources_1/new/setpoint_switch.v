`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06/25/2026 03:43:28 PM
// Design Name: 
// Module Name: setpoint_switch
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


module setpoint_switch(
    input wire clk,
    input wire rst_n,
    input wire sw_toggle,
    input wire [15:0] serial_setpoint,
    input wire [15:0] gpio_setpoint,
    
    output reg [15:0] setpoint_out
    );
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin 
            setpoint_out <= 16'b0;
        end else begin 
            setpoint_out <= sw_toggle ? gpio_setpoint : serial_setpoint; 
        end
    end 
endmodule
