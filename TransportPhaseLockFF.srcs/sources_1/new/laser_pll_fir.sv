`timescale 1ns / 1ps
// 32-tap real-coefficient FIR, evaluated at the last of each eight samples.
// Apply the identical filter to I and Q BEFORE decimation (not to phase).
module laser_pll_fir (
    input wire clk,
    input wire rst_n,
    input wire [143:0] samples,
    input wire samples_valid,
    output wire signed [23:0] filtered,
    output wire filtered_valid
);
    `include "laser_pll_fir_coeffs.vh"
    reg signed [17:0] history [0:23];
    wire signed [17:0] window_samples [0:31];
    reg signed [35:0] products [0:31];
    wire signed [36:0] sum1 [0:15];
    reg signed [37:0] sum2 [0:7];
    wire signed [38:0] sum3 [0:3];
    reg signed [39:0] sum4 [0:1];
    reg signed [40:0] sum5;
    reg [3:0] valid_pipe;
    reg [1:0] history_beats;
    for (genvar k = 0; k < 32; k = k + 1) begin : taps
        if (k < 8) assign window_samples[k] = samples[(7-k)*18 +: 18];
        else assign window_samples[k] = history[k-8];
        always @(posedge clk)
            products[k] <= window_samples[k] * fir_coefficient(k);
    end
    for (genvar k = 0; k < 16; k = k + 1)
        assign sum1[k] = $signed(products[2*k]) + $signed(products[2*k+1]);
    for (genvar k = 0; k < 4; k = k + 1)
        assign sum3[k] = $signed(sum2[2*k]) + $signed(sum2[2*k+1]);
    always @(posedge clk) begin
        if (!rst_n || !samples_valid) begin
            for (integer k = 0; k < 24; k = k + 1) history[k] <= 0;
            history_beats <= 0;
        end else begin
            for (integer k = 0; k < 8; k = k + 1) history[k] <= samples[(7-k)*18 +: 18];
            for (integer k = 8; k < 24; k = k + 1) history[k] <= history[k-8];
            if (history_beats != 3) history_beats <= history_beats + 1'b1;
        end
        if (!rst_n) valid_pipe <= 0;
        else valid_pipe <= {valid_pipe[2:0], samples_valid && history_beats == 3};
        for (integer k = 0; k < 8; k = k + 1)
            sum2[k] <= $signed(sum1[2*k]) + $signed(sum1[2*k+1]);
        for (integer k = 0; k < 2; k = k + 1)
            sum4[k] <= $signed(sum3[2*k]) + $signed(sum3[2*k+1]);
        sum5 <= $signed(sum4[0]) + $signed(sum4[1]);
    end
    // Q1.17 coefficients, retain eight fractional bits relative to ADC counts.
    wire signed [40:0] scaled = sum5 >>> 11;
    assign filtered = scaled > 8388607 ? 24'sh7fffff :
                      scaled < -8388608 ? 24'sh800000 : scaled[23:0];
    assign filtered_valid = valid_pipe[3];
endmodule
