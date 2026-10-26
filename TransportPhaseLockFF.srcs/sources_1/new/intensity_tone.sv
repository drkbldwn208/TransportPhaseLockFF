`timescale 1ns / 1ps
// Independent diagnostic DDS. Nothing here registers the feedback command.
// Cosine is Q1.15; envelope is Q1.12. Full on/off ramp: 1.067 ms.
module intensity_tone (
    input wire clk, rst_n, enable,
    input wire [31:0] frequency_word,
    input wire signed [15:0] amplitude_codes,
    output reg signed [17:0] dither,
    output reg [31:0] dither_phase,
    output wire active, ramping
);
    reg [31:0] phase, phase_s, phase_p, phase_scaled;
    (* rom_style="block" *) reg signed [15:0] cosine_rom [0:4095];
    initial $readmemh("intensity_cosine.mem", cosine_rom);
    reg signed [15:0] cosine;
    (* use_dsp="yes" *) reg signed [31:0] product;
    (* use_dsp="yes" *) reg signed [45:0] scaled;
    reg [12:0] envelope;
    reg [5:0] ramp_count;
    reg [3:0] tail;
    assign active=enable || envelope!=0 || (|tail);
    assign ramping=enable ? envelope!=4096 : active;
    always @(posedge clk) begin
        if (!rst_n) begin
            phase<=0; phase_s<=0; phase_p<=0; phase_scaled<=0;
            cosine<=0; product<=0; scaled<=0; dither<=0; dither_phase<=0;
            envelope<=0; ramp_count<=0; tail<=0;
        end else begin
            phase<=phase+frequency_word;
            cosine<=cosine_rom[phase[31:20]];
            // Reference is the actual ROM lookup angle (not its discarded bits).
            phase_s<={phase[31:20],20'b0};
            product<=cosine*amplitude_codes; phase_p<=phase_s;
            scaled<=product*$signed({1'b0,envelope}); phase_scaled<=phase_p;
            dither<=scaled >>> 27; dither_phase<=phase_scaled;
            tail<={tail[2:0],envelope!=0};
            ramp_count<=ramp_count+1'b1;
            if (&ramp_count) begin
                if (enable && envelope<4096) envelope<=envelope+1'b1;
                else if (!enable && envelope!=0) envelope<=envelope-1'b1;
            end
        end
    end
endmodule
