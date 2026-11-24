`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 11/23/2026 08:35:35 AM
// Design Name: 
// Module Name: gpio_word_cdc
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


module gpio_word_cdc #(
    parameter integer WIDTH = 32,
    parameter [WIDTH-1:0] INITIAL_WORD = 100
)(
    input wire gpio_clk,
    input wire [WIDTH-1:0] gpio_word,
    input wire clk,
    output reg [WIDTH-1:0] pl_word = INITIAL_WORD
    );
    
    reg [WIDTH-1:0] held_word = INITIAL_WORD;
    reg send = 1'b0;
    reg first = 1'b1;
    
    wire ack;
    wire valid;
    wire [WIDTH-1:0] received;
    
    always @(posedge gpio_clk) begin
        if (send) begin
            if (ack) 
                send <= 1'b0;
        end else if (!ack && (first || gpio_word != held_word)) begin
            held_word <= gpio_word;
            send <= 1'b1;
            first <= 1'b0;
        end
    end 
    
    xpm_cdc_handshake #(
        .WIDTH(WIDTH),
        .DEST_EXT_HSK(0)
    ) handshake (
        .src_clk(gpio_clk),
        .src_in(held_word),
        .src_send(send),
        .src_rcv(ack),
        .dest_clk(clk),
        .dest_out(received),
        .dest_req(valid),
        .dest_ack(1'b0)
    );
    
    always @(posedge clk) begin 
        if (valid)
            pl_word <= received;
        end 
        
endmodule
