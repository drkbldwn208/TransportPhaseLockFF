`timescale 1ns / 1ps
// Signed 24-bit cycle memory. One whole turn is 262144 phase codes.
// Saturate only at the numeric limits; never wrap a full counter through zero.
module laser_pll_unwrap #(
    parameter integer STAGE3_RANGE_SHIFT = 0
) (
    input wire clk,
    input wire rst_n,
    input wire arm,
    input wire phase_valid,
    input wire signed [17:0] phase_error,
    output reg signed [23:0] turns,
    output wire signed [42:0] unwrapped_error,
    output wire signed [25:0] phase_for_dac
);
    reg signed [17:0] previous_error;
    reg previous_valid;
    wire signed [18:0] jump = {phase_error[17],phase_error} -
                              {previous_error[17],previous_error};
    reg signed [23:0] next_turns;
    always @* begin
        next_turns = turns;
        if (!arm || !previous_valid) next_turns = 0;
        else if (jump < -19'sd131072 && turns<24'sh7fffff) next_turns = turns+1'b1;
        else if (jump >  19'sd131072 && turns>24'sh800000) next_turns = turns-1'b1;
    end
    // Use the updated turn count on the SAME sample as the wrapped crossing.
    assign unwrapped_error = $signed({next_turns[23],next_turns,18'b0}) +
                             $signed({{25{phase_error[17]}},phase_error});
    // Broaden only the DAC representation; slip memory remains 24 full turns
    // bits, and unwrapped_error remains 2^18 codes/turn. Discarding the lowest
    // phase bits before the existing DSP keeps its width/latency unchanged.
    // shift=0/1/2 gives full DAC spans 160/320/640 turns at gain shift zero.
    localparam integer LOCAL_BITS = 26 + STAGE3_RANGE_SHIFT;
    localparam integer TURN_BOUND = 128 << STAGE3_RANGE_SHIFT;
    wire signed [LOCAL_BITS-1:0] local_phase =
        $signed({next_turns[7+STAGE3_RANGE_SHIFT:0],18'b0}) +
        $signed({{(8+STAGE3_RANGE_SHIFT){phase_error[17]}},phase_error});
    assign phase_for_dac = next_turns>=TURN_BOUND ? 26'sh1ffffff :
                           next_turns<=-TURN_BOUND ? 26'sh2000000 :
                           local_phase >>> STAGE3_RANGE_SHIFT;
    always @(posedge clk) begin
        if (!rst_n || !phase_valid || !arm) begin
            turns <= 0; previous_error <= 0; previous_valid <= 0;
        end else begin
            previous_error <= phase_error; previous_valid <= 1;
            turns <= next_turns;
        end
    end
endmodule
