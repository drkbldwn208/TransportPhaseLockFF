`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 05/14/2026 12:26:54 PM
// Design Name: 
// Module Name: pmod_ad1_adc
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


module pmod_ad1_adc #(
    parameter CLK_DIV = 8
    ) (
    input wire clk,
    input wire rst_n,
    
    output reg adc_cs_n,
    output reg adc_sclk,
    input wire adc_sdata0,
    input wire adc_sdata1,
    // {4'b0, ch1[11:0], 4'b0, ch0[11:0]   
    output reg [31:0] m_axis_tdata,
    output reg m_axis_tvalid,
    input wire m_axis_tready,
    
    output reg out_sclk
    );
    
    localparam HALF = CLK_DIV/2;
    localparam IDLE = 2'd0;
    localparam SHIFT = 2'd1;
    localparam EMIT = 2'd2;
    
    reg [3:0] div;
    reg sclk_re, sclk_fe;
    reg [1:0] st;
    reg [4:0] bcnt;
    reg [15:0] sh0, sh1;
    
    always @(posedge clk) begin
        sclk_re <= 1'b0;
        sclk_fe <= 1'b0;
        if (!rst_n) begin
            div <= 4'b0;
            adc_sclk <= 1'b1;
        end else begin 
            div <= div + 4'd1;
            if (div == HALF-1) begin
                adc_sclk <= 1'b0;
                sclk_fe <= 1'b1;
            end 
            if (div == CLK_DIV-1) begin
                adc_sclk <= 1'b1;
                sclk_re <= 1'b1;
                div <= 4'b0;
            end 
        end
    end
    
    always @(posedge clk) begin
        if (!rst_n) begin
            st <= IDLE;
            adc_cs_n <= 1'b1;
            m_axis_tvalid <= 1'b0;
            m_axis_tdata <= 32'd0;
            bcnt <= 5'd0;
            sh0 <= 16'd0;
            sh1 <= 16'd0;
        end else begin
            case (st)
                IDLE: begin
                    adc_cs_n <= 1'b0; //assert cs, wait for sclk falling edge
                    bcnt <= 5'd16;
                    if (sclk_fe) st <= SHIFT;
                end
                
                SHIFT: begin
                    if (sclk_re) begin //sample on rising edge
                        sh0 <= {sh0[14:0], adc_sdata0};
                        sh1 <= {sh1[14:0], adc_sdata1};
                        bcnt <= bcnt - 5'd1;
                        if (bcnt == 5'd1) st <= EMIT;
                    end
                end
                
                EMIT: begin
                    adc_cs_n <= 1'b1; // release cs, wait for time tquiet (~ 50 ns, faster than divider period)
                    m_axis_tdata <= {4'b0, sh1[11:0], 4'b0, sh0[11:0]};
                    m_axis_tvalid <= 1'b1;
                    if (m_axis_tvalid && m_axis_tready) begin 
                        m_axis_tvalid <= 1'b0;
                        st <= IDLE;
                    end
                end
                
                default: st <= IDLE;
            endcase
        end
    end 

endmodule
