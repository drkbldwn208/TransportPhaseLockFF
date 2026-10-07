`timescale 1ns / 1ps
// Signed 24-bit cycle memory. One whole turn is 262144 phase codes.
// Saturate only at the numeric limits; never wrap a full counter through zero.
module laser_pll_unwrap (
    input wire clk,
    input wire rst_n,
    input wire arm,
    input wire phase_valid,
    input wire signed [17:0] phase_error,
    output reg signed [23:0] turns,
    output wire signed [42:0] unwrapped_error,
    output wire signed [17:0] phase_for_dac
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
    // With available phase gains >=1, ANY nonzero whole-turn count rails the
    // DAC. Clip before the gain shifter to keep wide counters off the fast adder.
    // This is exactly the same 16-bit saturated output as scaling all 43 bits.
    assign phase_for_dac = next_turns>0 ? 18'sh1ffff :
                           next_turns<0 ? 18'sh20000 : phase_error;
    always @(posedge clk) begin
        if (!rst_n || !phase_valid || !arm) begin
            turns <= 0; previous_error <= 0; previous_valid <= 0;
        end else begin
            previous_error <= phase_error; previous_valid <= 1;
            turns <= next_turns;
        end
    end
endmodule
