`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 11/23/2026 08:13:33 AM
// Design Name: 
// Module Name: hist_counter
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


module counts_average(
    input wire clk,
    input wire rst_n,
    
    input wire gpio_clk,
    input wire [15:0] gpio_ncycles,

    input wire input_edge,
  
    output reg [15:0] m_axis_tdata,
    output reg m_axis_tvalid,
    input wire m_axis_tready
    );
    
    wire [15:0] ncycles;
    
    reg [15:0] ncycles_stable = 16'd100;
    
    gpio_word_cdc  #(
        .WIDTH(16),
        .INITIAL_WORD(100)
    ) u_ncycles_cdc (
        .gpio_clk(gpio_clk),
        .gpio_word(gpio_ncycles),
        .clk(clk),
        .pl_word(ncycles)
    );
    
    
    reg [15:0] cycles_counter = 16'd1; 
    reg [15:0] counts = 16'b0;
    
    wire [15:0] counts_next = counts + input_edge;
    
    always @(posedge clk) begin
        if (!rst_n) begin
            cycles_counter <= 16'd1;        
            ncycles_stable <= 16'd100;
            counts <= 32'b0;
            m_axis_tdata <= 16'd0;
            m_axis_tvalid <= 1'b0;
        end else begin
            if (cycles_counter == ncycles_stable) begin
                m_axis_tdata <= counts_next;
                m_axis_tvalid <= 1'b1;
                counts <= 16'd0;
                cycles_counter <= 16'd1;
                ncycles_stable <= ncycles;
            end else begin 
                m_axis_tdata <= 16'd0;
                m_axis_tvalid <= 1'b0;                
                counts <= counts_next;
                cycles_counter <= cycles_counter + 16'd1;
            end
        end 
    end 
             
endmodule
