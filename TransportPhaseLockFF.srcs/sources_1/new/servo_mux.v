`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 11/24/2026 05:47:05 PM
// Design Name: 
// Module Name: servo_mux
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


module servo_mux(
    input wire clk,
    input wire rst_n, 
    
    input wire gpio_clk,
    input wire gpio_sel,
    input wire [31:0] gpio_dur,
    
    
    input wire trigger,
    
    input wire [15:0] dac_command_1,
    
    input wire [15:0] s_axis_tdata,
    input wire s_axis_tvalid,
    output wire s_axis_tready,
    
    output wire [15:0] dac_command_muxed,
    output wire photon_active
    );
    
    wire sel;
    reg sel_stable;
    
    reg [31:0] timer;
    
    wire [31:0] dur_wire;
    reg [31:0] duration;
    
    reg is_active;
    reg [15:0] latched_dac_command;
    
    reg trig_last;
    
    gpio_word_cdc #(
        .WIDTH(1),
        .INITIAL_WORD(0)
        ) sel_cdc (
        .gpio_clk(gpio_clk),
        .gpio_word(gpio_sel),
        .clk(clk),
        .pl_word(sel)
    );
    

    gpio_word_cdc #(
        .WIDTH(32),
        .INITIAL_WORD(100)
        ) duration_cdc (
        .gpio_clk(gpio_clk),
        .gpio_word(gpio_dur),
        .clk(clk),
        .pl_word(dur_wire)
    );
    
    always @(posedge clk) begin
        if (!rst_n) begin
            sel_stable <= 1'b0;
            timer <= 32'd0;
            trig_last <= 1'b0;
            duration <= 32'd100;
            is_active <= 1'b0;
            latched_dac_command <= 16'd0;
        end else begin 
            sel_stable <= sel;
            trig_last <= trigger;
            if (is_active) begin
                if (s_axis_tvalid)
                    latched_dac_command <= s_axis_tdata;                
                timer <= timer + 32'd1;
                if (timer == duration - 32'd1) begin
                    timer <= 32'd0;
                    is_active <= 1'b0;
                end
            end else if (sel_stable && trigger && !trig_last && dur_wire != 0) begin
                is_active <= 1'b1;
                duration <= dur_wire;
                timer <= 32'd0;
            end else
                latched_dac_command <= 16'd0;
        end                        
    end
    
    assign dac_command_muxed = sel_stable ? latched_dac_command : dac_command_1;
    assign s_axis_tready = 1'b1;
    assign photon_active = sel_stable && is_active;
    
endmodule
