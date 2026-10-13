`timescale 1ns / 1ps
// Diagnostic-only phase relative to the start of a measurement block.
// Preserve the CORDIC's 2^18 codes/turn; the signed 20-bit probe spans +/-2 turns.
// Modulo differencing crosses +/-pi without a sawtooth. Overflow rails/flags the
// measurement, never changes the separate feedback winding accumulator.
module laser_pll_phase_probe (
    input wire clk, rst_n, active,
    input wire signed [17:0] phase,
    input wire phase_valid,
    output reg signed [19:0] relative_phase,
    output reg valid, saturated
);
    reg signed [17:0] previous_phase;
    reg have_previous;
    wire signed [17:0] difference = phase-previous_phase;
    wire signed [20:0] next_phase = $signed(relative_phase)+$signed(difference);
    always @(posedge clk) begin
        if (!rst_n) begin
            previous_phase<=0; have_previous<=0; relative_phase<=0; valid<=0; saturated<=0;
        end else begin
            valid<=phase_valid;
            if (phase_valid) previous_phase<=phase;
            if (!active) begin
                have_previous<=phase_valid; relative_phase<=0; saturated<=0;
            end else if (phase_valid) begin
                have_previous<=1;
                if (!have_previous) relative_phase<=0;
                else if (next_phase>524287) begin relative_phase<=20'sh7ffff; saturated<=1; end
                else if (next_phase< -524288) begin relative_phase<=20'sh80000; saturated<=1; end
                else relative_phase<=next_phase[19:0];
            end
        end
    end
endmodule
