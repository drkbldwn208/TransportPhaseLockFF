`timescale 1ns / 1ps
// Manual stage requests, qualified in hardware, with a temporary tracking offset.
// Once offset==0 this is one register, with no smoothing of phase fluctuations.
module laser_pll_handoff (
    input wire clk,
    input wire rst_n,
    input wire ready,
    input wire [2:0] requested_mode,
    input wire request_allowed,
    input wire [3:0] ramp_interval_log2,
    input wire signed [15:0] requested_target,
    input wire requested_valid,
    input wire signed [15:0] active_target,
    input wire active_valid,
    input wire active_saturated,
    output reg [2:0] active_mode,
    output reg signed [15:0] dac_target,
    output reg target_valid,
    output reg target_saturated,
    output wire transitioning
);
    reg signed [17:0] tracking_offset;
    reg [14:0] ramp_count;
    reg started;
    wire [14:0] ramp_mask = (16'd1 << ramp_interval_log2)-1'b1;
    wire change = (!started || requested_mode!=active_mode) && request_allowed && requested_valid;
    wire signed [17:0] corrected = $signed({{2{active_target[15]}},active_target}) + tracking_offset;
    assign transitioning = tracking_offset!=0;
    always @(posedge clk) begin
        if (!rst_n) begin
            active_mode <= 0; dac_target <= 0; target_valid <= 0;
            target_saturated <= 0; tracking_offset <= 0; ramp_count <= 0;
            started <= requested_mode==0;
        end else if (ready) begin
            if (change) begin
                active_mode <= requested_mode;
                started <= 1;
                // The first sample after a stage change equals the previous
                // output exactly, including when another transition is active.
                tracking_offset <= $signed({{2{dac_target[15]}},dac_target}) -
                                   $signed({{2{requested_target[15]}},requested_target});
                target_valid <= 1; target_saturated <= 0; ramp_count <= 0;
            end else if (!started || !active_valid) begin
                dac_target <= 0; target_valid <= 0; target_saturated <= 0;
                tracking_offset <= 0; ramp_count <= 0;
            end else begin
                target_valid <= 1;
                target_saturated <= active_saturated || corrected>32767 || corrected < -32768;
                dac_target <= corrected>32767 ? 16'sh7fff :
                              corrected < -32768 ? 16'sh8000 : corrected[15:0];
                ramp_count <= (ramp_count+1'b1) & ramp_mask;
                if (ramp_count==ramp_mask) begin
                    if (tracking_offset>0) tracking_offset <= tracking_offset-1'b1;
                    else if (tracking_offset<0) tracking_offset <= tracking_offset+1'b1;
                end
            end
        end
    end
endmodule
