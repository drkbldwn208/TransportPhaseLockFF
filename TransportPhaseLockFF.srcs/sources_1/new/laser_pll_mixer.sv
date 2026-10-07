`timescale 1ns / 1ps
// Real ADC samples -> I+jQ = x * exp(-j*reference_phase).
// 8 chronological 16-bit samples/clock, lane 0 earliest. No backpressure.
module laser_pll_mixer (
    input wire clk,
    input wire rst_n,
    input wire [127:0] adc_data,
    input wire adc_valid,
    input wire [31:0] frequency_low,
    input wire [31:0] frequency_high,
    output wire [143:0] i_data,
    output wire [143:0] q_data,
    output wire mixed_valid,
    output reg frequency_ack,
    output wire [47:0] committed_frequency
);
    reg [47:0] phase_accumulator = 0;
    reg [47:0] frequency_word = 0;
    assign committed_frequency = frequency_word;
    reg [3:0] valid_pipe = 0;
    wire commit = frequency_high[16] != frequency_ack;
    // Commit latches both GPIO words atomically. Frequency changes preserve phase.
    // Bit 17 requests an explicit phase restart, intended only while muted.
    always @(posedge clk) begin
        if (!rst_n) begin
            phase_accumulator <= 0;
            frequency_word <= 0;
            frequency_ack <= 0;
            valid_pipe <= 0;
        end else begin
            phase_accumulator <= phase_accumulator + (frequency_word << 3);
            if (commit) begin
                frequency_word <= {frequency_high[15:0], frequency_low};
                frequency_ack <= frequency_high[16];
                if (frequency_high[17]) phase_accumulator <= 0;
            end
            // Keep physical time even when ADC valid drops or the output is muted.
            valid_pipe <= {valid_pipe[2:0], adc_valid};
        end
    end
    assign mixed_valid = valid_pipe[3];

    for (genvar lane = 0; lane < 8; lane = lane + 1) begin : lanes
        reg [15:0] phase;
        wire [15:0] cosine_phase = phase + 16'h4000;
        wire [13:0] sin_address = phase[14] ? ~phase[13:0] : phase[13:0];
        wire [13:0] cos_address = cosine_phase[14] ? ~cosine_phase[13:0] : cosine_phase[13:0];
        wire [47:0] lane_phase = phase_accumulator + lane * frequency_word;
        (* rom_style = "block" *) reg [17:0] sine_rom [0:16383];
        initial $readmemh("laser_pll_sine.mem", sine_rom);
        reg [17:0] sin_magnitude, cos_magnitude;
        reg sin_negative, cos_negative;
        reg signed [17:0] sine, cosine;
        reg signed [15:0] sample0, sample1, sample2;
        reg signed [33:0] product_i, product_q;
        always @(posedge clk) begin
            phase <= lane_phase[47:32];
            sample0 <= adc_data[16*lane +: 16];
            sin_magnitude <= sine_rom[sin_address];
            cos_magnitude <= sine_rom[cos_address];
            sin_negative <= phase[15];
            cos_negative <= cosine_phase[15];
            sample1 <= sample0;
            sine <= sin_negative ? -$signed(sin_magnitude) : $signed(sin_magnitude);
            cosine <= cos_negative ? -$signed(cos_magnitude) : $signed(cos_magnitude);
            sample2 <= sample1;
            product_i <= sample2 * cosine;
            product_q <= sample2 * (-sine);
        end
        // Keep two fractional ADC bits for the FIR and phase calculation.
        assign i_data[18*lane +: 18] = product_i[32:15];
        assign q_data[18*lane +: 18] = product_q[32:15];
    end
endmodule
