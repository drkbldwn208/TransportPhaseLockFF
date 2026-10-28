`timescale 1ns / 1ps
// RFDC complex Fs=983.04 MS/s, four chronological I/Q samples per 245.76 MHz
// clock. Average four lanes, then a unity-DC-gain 15-tap FIR on each quadrature.
// The 180 MHz image folds to 65.76 MHz after lane averaging. FIR stopband begins
// at 55 MHz; quantized rejection >86 dB, passband droop <0.035 dB at 1.5 MHz.
// Replication preserves the PI's four-lane interface and ADC-count units.
module intensity_rx_lowpass (
    input wire clk,
    input wire rst_n,
    input wire [63:0] i_data, q_data,
    input wire sample_valid,
    output wire [63:0] filtered_i, filtered_q,
    output wire filtered_valid
);
    wire signed [15:0] i_out, q_out;
    intensity_rx_fir fir_i (.clk(clk), .rst_n(rst_n), .samples(i_data),
        .sample_valid(sample_valid), .filtered(i_out));
    intensity_rx_fir fir_q (.clk(clk), .rst_n(rst_n), .samples(q_data),
        .sample_valid(sample_valid), .filtered(q_out));
    // Covers all 15 taps and the arithmetic pipeline; a gap invalidates the
    // complete affected window. The diagnostic reports it instead of hiding it.
    reg [17:0] valid_history;
    always @(posedge clk) begin
        if (!rst_n) valid_history <= 0;
        else valid_history <= {valid_history[16:0], sample_valid};
    end
    assign filtered_valid = &valid_history;
    assign filtered_i = {4{i_out}};
    assign filtered_q = {4{q_out}};
endmodule

module intensity_rx_fir (
    input wire clk, rst_n,
    input wire [63:0] samples,
    input wire sample_valid,
    output reg signed [15:0] filtered
);
    // Coefficients / 2^18; sum is exactly 2^18, all positive (no overshoot).
    localparam signed [17:0] H [0:14] = '{
        243,1423,4698,11113,20616,31342,39982,43310,
        39982,31342,20616,11113,4698,1423,243};
    wire signed [17:0] lane0 = {{2{samples[15]}},samples[15:0]};
    wire signed [17:0] lane1 = {{2{samples[31]}},samples[31:16]};
    wire signed [17:0] lane2 = {{2{samples[47]}},samples[47:32]};
    wire signed [17:0] lane3 = {{2{samples[63]}},samples[63:48]};
    reg signed [17:0] sum_lanes;
    (* use_dsp = "yes" *) reg signed [35:0] product [0:14];
    (* use_dsp = "yes" *) reg signed [35:0] accum [0:14];
    wire signed [35:0] rounded = accum[0] + 36'sd524288;
    integer k;
    always @(posedge clk) begin
        if (!rst_n) begin
            sum_lanes <= 0;
            filtered <= 0;
            for (k=0; k<15; k=k+1) begin product[k]<=0; accum[k]<=0; end
        end else begin
            sum_lanes <= sample_valid ? lane0+lane1+lane2+lane3 : 18'sd0;
            // Transposed FIR: registered products then one add per tap/clock.
            for (k=0; k<15; k=k+1) product[k] <= sum_lanes * H[k];
            accum[14] <= product[14];
            for (k=0; k<14; k=k+1) accum[k] <= product[k] + accum[k+1];
            // Divide by four lanes and by the coefficient scale only once.
            // Positive unity-sum coefficients guarantee no 16-bit overflow.
            filtered <= rounded >>> 20;
        end
    end
endmodule
