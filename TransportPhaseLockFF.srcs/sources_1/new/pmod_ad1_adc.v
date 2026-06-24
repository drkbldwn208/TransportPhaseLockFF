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


module pmod_ad1_adc (
    input wire clk,
    input wire rst_n,
    
    output reg adc_cs_n,
    output wire adc_sclk,
    input wire adc_sdata0,
    input wire adc_sdata1,
    // {4'b0, ch1[11:0], 4'b0, ch0[11:0]   
    output reg [31:0] m_axis_tdata,
    output reg m_axis_tvalid,
    input wire m_axis_tready,
    
    output reg out_sclk
    );
    
    localparam [4:0] FRAME_LAST_PHASE = 5'd19;
    localparam [4:0] CONV_LAST_PHASE = 5'd15;
    
    reg [4:0] phase_count;
    reg [4:0] fall_count;
    reg [11:0] sh0;
    reg [11:0] sh1;
    
    assign adc_sclk = adc_cs_n ? 1'b1 : clk;
    
    
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin 
            phase_count <= FRAME_LAST_PHASE;
            adc_cs_n <= 1'b1;
            m_axis_tdata <= 32'b0;
            m_axis_tvalid <= 1'b0;
            out_sclk <= 1'b0;
        end else begin 
            if (m_axis_tvalid && m_axis_tready) begin
                m_axis_tvalid <= 1'b0; 
            end 
            out_sclk <= 1'b0;
            
            if (phase_count == FRAME_LAST_PHASE) begin 
                phase_count <= 5'd0;
                adc_cs_n <= 1'b0;
            end else begin 
                phase_count <= phase_count + 5'd1;
                
                if (phase_count == CONV_LAST_PHASE) begin 
                    adc_cs_n <= 1'b1;
                    m_axis_tdata <= {1'b0, sh1[11:0], 3'b0, 1'b0, sh0[11:0], 3'b0};
                    m_axis_tvalid <= 1'b1;
                    out_sclk <= 1'b1;
                end
            end
        end
    end 
    
    
    always @(negedge clk or negedge rst_n) begin 
        if (!rst_n) begin 
            sh0 <= 12'b0;
            sh1 <= 12'b0;
            fall_count <= 5'b0;
        end else begin
            if (adc_cs_n) begin 
                fall_count <= 5'b0;
            end else begin 
                if (fall_count >= 5'd4 && fall_count <= 5'd15) begin 
                    sh0 <= {sh0[10:0], adc_sdata0};
                    sh1 <= {sh1[10:0], adc_sdata1};
                end 
                
                if (fall_count < 5'd16) begin 
                    fall_count <= fall_count + 1; 
                end
            end
       end
   end 
    
    
endmodule
