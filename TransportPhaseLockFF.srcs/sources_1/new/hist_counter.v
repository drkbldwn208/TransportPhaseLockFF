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
    
    input wire trigger,
    input wire input_edge,
  
    output reg [31:0] m_axis_tdata,
    output reg m_axis_tvalid,
    output reg m_axis_tlast,
    input wire m_axis_tready
    );
    
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
    
    reg is_active = 1'b0;
    reg overflow_pending = 1'b0;
    reg [31:0] cycles_counter = 32'd1;
    reg [31:0] bins_counter = 32'd1;
    reg [31:0] counts = 32'd0;
    wire [31:0] counts_next = counts + input_edge;
    wire output_free = !m_axis_tvalid || m_axis_tready;

    // Bins measure wall-clock time: never stretch them to wait for a DMA.
    // The downstream 4096-word FIFO absorbs stalls. If it fills, finish with
    // an explicit 0x80000000 invalid-record marker rather than lose bins silently.
    // At one event/clock, valid counts cannot exceed 0x7fffffff because ncycles
    // is restricted to that value. A record is retriggered only after TLAST drains.
    always @(posedge clk) begin
        if (!rst_n) begin
            is_active <= 1'b0;
            overflow_pending <= 1'b0;
            cycles_counter <= 32'd1;
            bins_counter <= 32'd1;
            nbins_stable <= 32'd100;
            ncycles_stable <= 32'd100;
            counts <= 0;
            m_axis_tdata <= 0;
            m_axis_tvalid <= 0;
            m_axis_tlast <= 0;
        end else begin
            if (m_axis_tvalid && m_axis_tready) begin
                m_axis_tvalid <= 0;
                m_axis_tlast <= 0;
            end
            if (!is_active && !overflow_pending) begin
                nbins_stable <= nbins;
                ncycles_stable <= ncycles;
                if (!m_axis_tvalid && trigger && nbins_stable != 0 &&
                    ncycles_stable != 0 && !ncycles_stable[31]) begin
                    is_active <= 1;
                    cycles_counter <= 1;
                    bins_counter <= 1;
                    counts <= 0;
                end
            end
            if (is_active) begin
                if (cycles_counter == ncycles_stable) begin
                    cycles_counter <= 1;
                    counts <= 0;
                    if (output_free) begin
                        m_axis_tdata <= counts_next;
                        m_axis_tvalid <= 1;
                        m_axis_tlast <= bins_counter == nbins_stable;
                        bins_counter <= bins_counter + 1;
                        if (bins_counter == nbins_stable) is_active <= 0;
                    end else begin
                        is_active <= 0;
                        overflow_pending <= 1;
                    end
                end else begin
                    cycles_counter <= cycles_counter + 1;
                    counts <= counts_next;
                end
            end
            if (overflow_pending && output_free) begin
                m_axis_tdata <= 32'h80000000;
                m_axis_tvalid <= 1;
                m_axis_tlast <= 1;
                overflow_pending <= 0;
            end
        end
    end
endmodule
