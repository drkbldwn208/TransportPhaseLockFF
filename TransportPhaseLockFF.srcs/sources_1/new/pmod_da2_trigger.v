`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/21/2026 06:25:10 PM
// Design Name: 
// Module Name: pmod_da2_trigger
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


module pmod_da2_trigger(
    input wire clk,
    input wire trigger_in,
    output reg dac_cs = 1'b1,
    output reg dac_sclk = 1'b0,
    output reg dac_mosi = 1'b0
    );
    
    reg last_trigger = 1'b0;
    reg [15:0] shift_reg = 16'h0000;
    reg [4:0] bit_counter = 0;
    reg [2:0] clk_div = 0;
    reg busy = 1'b0;
    
    reg toggle_state = 1'b0;
    
    always @(posedge clk) begin
        last_trigger <= trigger_in;
        
        if ((trigger_in != last_trigger) && !busy) begin
            busy <= 1'b1;
            toggle_state <= ~toggle_state;
            
            //DA2 4 control bits + 12 data bits, 0x0FFF = 3.3 V, 0x0000 = 0 V
            
            shift_reg <= toggle_state ? 16'h0000 : 16'h0FFF;
            bit_counter <= 16;
            dac_cs <= 1'b0;
            
        end
            
        if (busy) begin
            clk_div <= clk_div + 1;
            
            if (clk_div == 3'd3) begin
                dac_sclk <= 1'b1;
            end else if (clk_div == 3'd7) begin
                dac_sclk <= 1'b0; 
                dac_mosi <= shift_reg[15];
                shift_reg <= {shift_reg[14:0], 1'b0};
                
                if (bit_counter > 0) begin
                    bit_counter <= bit_counter - 1;
                end else begin 
                    busy <= 1'b0;
                    dac_cs <= 1'b1;
                end
            end
        end
    end               
endmodule
