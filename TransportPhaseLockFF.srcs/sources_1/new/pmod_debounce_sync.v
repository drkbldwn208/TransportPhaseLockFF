`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06/26/2026 12:22:15 PM
// Design Name: 
// Module Name: pmod_debounce_sync
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


module pmod_debounce_sync #(
    parameter integer DEBOUNCE_CYCLES = 5,
    parameter integer EDGE_MODE = 1,
    parameter integer INITIAL_LEVEL = 0
    )(
    input wire clk,
    input wire rst_n,
    input wire async_pin,
    input wire clear_latch,
    
    output reg debounced_level, 
    output reg event_pulse,
    output reg event_latched
    );
    
    localparam integer COUNT_WIDTH = (DEBOUNCE_CYCLES <= 1) ? 1: $clog2(DEBOUNCE_CYCLES);
    
    (* ASYNC_REG = "TRUE" *) reg sync_meta;
    (* ASYNC_REG = "TRUE" *) reg sync_pin;
    
    reg [COUNT_WIDTH-1:0] stable_count;
    
    wire level_changed = (sync_pin != debounced_level);
    wire debounce_done = (DEBOUNCE_CYCLES <= 1) || (stable_count == DEBOUNCE_CYCLES - 1);
    
    wire accepted_rising_edge = (debounced_level == 1'b0) && (sync_pin == 1'b1);
    wire accepted_falling_edge = (debounced_level == 1'b1) && (sync_pin == 1'b0);
    
    wire selected_edge = 
        ((EDGE_MODE == 0) && accepted_falling_edge) ||
        ((EDGE_MODE == 1) && accepted_rising_edge) ||
        ((EDGE_MODE == 2) && (accepted_rising_edge || accepted_falling_edge));
    
    always @(posedge clk) begin 
        if (!rst_n) begin 
            sync_meta <= INITIAL_LEVEL[0];
            sync_pin <= INITIAL_LEVEL[0];
            debounced_level <= INITIAL_LEVEL[0];
            stable_count <= {COUNT_WIDTH{1'b0}};
            event_pulse <= 1'b0;
            event_latched <= 1'b0;
        end else begin 
            sync_meta <= async_pin;
            sync_pin <= sync_meta;
            event_pulse <= 1'b0;
            
            if (clear_latch) 
                event_latched <= 1'b0;
            
            if (level_changed) begin 
                if (debounce_done) begin 
                    debounced_level <= sync_pin;
                    stable_count <= {COUNT_WIDTH{1'b0}};
                    
                    if (selected_edge) begin 
                        event_pulse <= 1'b1;
                        event_latched <= 1'b1;
                    end 
                end else begin 
                    stable_count <= stable_count + 1'b1;
                end 
            end else begin 
                stable_count <= {COUNT_WIDTH{1'b0}};
            end
        end
    end 
endmodule
