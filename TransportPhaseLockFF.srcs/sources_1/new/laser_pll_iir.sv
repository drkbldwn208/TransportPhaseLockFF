`timescale 1ns / 1ps
// Optional first-order lead/lag: y[k]=b0*x[k]+b1*x[k-1]+p*y[k-1].
// One update every two RF clocks (122.88 MS/s). Two registered arithmetic
// stages let the recursive multiplier and saturating sum meet 245.76 MHz.
// Bypass is combinational: no additional feedback registers in that setting.
module laser_pll_iir (
    input wire clk, rst_n,
    input wire signed [15:0] input_code,
    input wire input_valid, input_saturated,
    input wire [31:0] control, b0_word, b1_word, pole_word,
    output wire signed [15:0] output_code,
    output wire output_valid, output_saturated,
    output wire [31:0] status
);
    // b0,b1: signed Q5.27; p: signed Q1.31. State: DAC codes with 24
    // fractional bits. Internal saturation prevents arithmetic wrap/windup.
    reg signed [31:0] b0, b1, pole;
    reg signed [39:0] state;
    reg signed [15:0] previous_raw;
    reg signed [16:0] previous_input;
    // Pair averaging suppresses the Nyquist noise that would alias to DC at
    // the half-rate update. Keep the half-code bit through the multipliers.
    wire signed [16:0] input_pair = $signed(input_code) + $signed(previous_raw);
    reg commit_ack, phase, sample_valid, sample_saturated, valid, saturated, previous_saturated;
    (* use_dsp="yes" *) reg signed [48:0] feed0, feed1;
    (* use_dsp="yes" *) reg signed [71:0] feedback;
    wire commit = control[1]!=commit_ack;
    wire signed [76:0] feed0_wide = {{28{feed0[48]}},feed0};
    wire signed [76:0] feed1_wide = {{28{feed1[48]}},feed1};
    wire signed [76:0] sum = (feed0_wide <<< 27) + (feed1_wide <<< 27) +
                            $signed(feedback) + 77'sd1073741824;
    wire signed [45:0] rounded_state = sum >>> 31;
    wire state_clip = rounded_state>46'sd549755813887 || rounded_state < -46'sd549755813888;
    wire signed [40:0] rounded_output = $signed(state) + 41'sd8388608;
    wire signed [16:0] integer_output = rounded_output >>> 24;
    wire output_clip = integer_output>32767 || integer_output < -32768;
    wire signed [15:0] filtered = integer_output>32767 ? 16'sh7fff :
                                 integer_output < -32768 ? 16'sh8000 : integer_output[15:0];
    always @(posedge clk) begin
        if (!rst_n) begin
            b0<=32'sd134217728; b1<=0; pole<=0; state<=0; previous_input<=0; previous_raw<=0;
            commit_ack<=0; previous_saturated<=0; phase<=0; sample_valid<=0; sample_saturated<=0;
            valid<=0; saturated<=0; feed0<=0; feed1<=0; feedback<=0;
        end else if (commit || !input_valid) begin
            // Warm the filter from the current DC level. Exact for unity DC
            // gain; other DC gains must settle in bypass before selection.
            state<={input_code,24'b0}; previous_input<={input_code,1'b0}; previous_raw<=input_code;
            phase<=0; valid<=0; saturated<=0; sample_valid<=0; previous_saturated<=input_saturated;
            if (commit) begin b0<=b0_word; b1<=b1_word; pole<=pole_word; commit_ack<=control[1]; end
        end else begin
            phase<=~phase; previous_raw<=input_code; previous_saturated<=input_saturated;
            if (!phase) begin
                feed0<=input_pair*b0; feed1<=previous_input*b1; feedback<=state*pole;
                previous_input<=input_pair; sample_valid<=input_valid; sample_saturated<=input_saturated || previous_saturated;
            end else begin
                state<=rounded_state>46'sd549755813887 ? 40'sh7fffffffff :
                       rounded_state < -46'sd549755813888 ? 40'sh8000000000 : rounded_state[39:0];
                valid<=sample_valid; saturated<=sample_saturated || state_clip;
            end
        end
    end
    assign output_code = control[0] ? filtered : input_code;
    assign output_valid = control[0] ? valid : input_valid;
    assign output_saturated = control[0] ? (saturated || output_clip) : input_saturated;
    assign status = {28'b0,valid,(saturated || output_clip),commit_ack,control[0]};
endmodule
