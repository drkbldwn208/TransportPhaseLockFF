`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06/23/2026 03:01:50 PM
// Design Name: 
// Module Name: cordic_phase_helper
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


module cordic_phase_helper(
    input wire clk,
    
    input wire [15:0] gpio_phase_in,
    
    output reg [15:0] m_axis_phase_tdata,
    output reg m_axis_phase_tvalid
    );
    
    always @(posedge clk) begin
        m_axis_phase_tdata <= gpio_phase_in;
        m_axis_phase_tvalid <= 1'b1;
    end 

endmodule
