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


module hist_counter(
    input wire clk,
    input wire rst_n,
    
    input wire gpio_clk,
    input wire [31:0] gpio_nbins,
    input wire [31:0] gpio_ncycles,
    input wire gpio_arm,
    
    input wire trigger,
    input wire input_edge,
  
    output reg [31:0] m_axis_tdata,
    output reg m_axis_tvalid,
    output reg m_axis_tlast,
    input wire m_axis_tready
    );
    
    wire arm;
    wire [31:0] nbins;
    wire [31:0] ncycles;
    
    reg [31:0] nbins_stable = 32'd100;
    reg [31:0] ncycles_stable = 32'd100;
    
    gpio_word_cdc u_nbins_cdc (
        .gpio_clk(gpio_clk),
        .gpio_word(gpio_nbins),
        .clk(clk),
        .pl_word(nbins)
    );
    
    gpio_word_cdc u_ncycles_cdc (
        .gpio_clk(gpio_clk),
        .gpio_word(gpio_ncycles),
        .clk(clk),
        .pl_word(ncycles)
    );
    
    gpio_word_cdc #(
        .WIDTH(1),
        .INITIAL_WORD(0)
        ) arm_cdc (
        .gpio_clk(gpio_clk),
        .gpio_word(gpio_arm),
        .clk(clk),
        .pl_word(arm)
    );
    
    reg is_active = 1'b0;
    reg is_armed = 1'b1;
    reg [31:0] cycles_counter = 32'd1;
    reg [31:0] bins_counter = 32'd1; 
    reg [31:0] counts = 32'b0;
    
    wire [31:0] counts_next = counts + input_edge;
    
    always @(posedge clk) begin
        if (!rst_n) begin
            is_active <= 1'b0;
            is_armed <= 1'b0;
            cycles_counter <= 32'd1;        
            bins_counter <= 32'd1;
            nbins_stable <= 32'd100;
            ncycles_stable <= 32'd100;
            counts <= 32'b0;
            m_axis_tdata <= 32'd0;
            m_axis_tvalid <= 1'b0;
            m_axis_tlast <= 1'b0;
        end else begin
        
            if (!is_active) begin
                nbins_stable <= nbins;
                ncycles_stable <= ncycles;
                m_axis_tlast <= 1'b0;
                m_axis_tvalid <= 1'b0;
            end 
            
            if (arm & ~is_armed) 
                is_armed <= 1'b1;
            
            if (!is_active && m_axis_tready && trigger && is_armed)
                is_active <= 1'b1;
                
            if (is_active) begin
                
                if (cycles_counter == ncycles_stable) begin
                    m_axis_tdata <= counts_next;
                    m_axis_tvalid <= 1'b1;
                    
                    counts <= 32'd0;
                    bins_counter <= bins_counter + 32'd1;
                    cycles_counter <= 32'd1;
                    if (bins_counter == nbins_stable) begin
                        m_axis_tlast <= 1'b1;
                        is_active <= 1'b0; 
                        is_armed <= 1'b0;
                        bins_counter <= 32'd1;
                    end
                    
                end else begin 
                    m_axis_tdata <= 32'd0;
                    m_axis_tvalid <= 1'b0;
                    m_axis_tlast <= 1'b0;
                    
                    counts <= counts_next;
                    cycles_counter <= cycles_counter + 32'd1;
                end
            end 
        end 
   end   
             
endmodule
