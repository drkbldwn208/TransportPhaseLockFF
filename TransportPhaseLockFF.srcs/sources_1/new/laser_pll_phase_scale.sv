`timescale 1ns / 1ps
// Stage 3: full DAC span = 160 turns / 2^gain_shift (approximately).
// Input phase has 2^18 codes/turn and is bounded to +/-128 turns upstream.
// Three registers: phase/control, reciprocal product, rounded/clipped DAC.
module laser_pll_phase_scale (
    input wire clk,
    input wire rst_n,
    input wire signed [25:0] phase_codes,
    input wire phase_valid,
    input wire [3:0] gain_shift,
    input wire invert,
    output reg signed [15:0] dac_target,
    output reg target_valid,
    output reg saturated
);
    reg signed [25:0] phase_reg;
    reg [3:0] gain1, gain2;
    reg invert1, invert2, valid1, valid2;
    // 104858/2^26 approximates 1/640: 1/4 converts phase codes to DAC
    // codes, then 1/160 widens the phase range. Relative error = +3.815 ppm;
    // <0.126 DAC code at either rail. One 26x18-bit DSP multiplication.
    (* use_dsp = "yes" *) reg signed [43:0] product;
    wire [5:0] right_shift = 6'd26 - {2'b0,gain2};
    wire signed [43:0] signed_product = invert2 ? -product : product;
    // Round to nearest (half-code ties toward +infinity), then saturate.
    wire signed [43:0] rounded = signed_product + (44'sd1 <<< (right_shift-1'b1));
    wire signed [43:0] scaled = rounded >>> right_shift;
    always @(posedge clk) begin
        if (!rst_n) begin
            phase_reg <= 0; gain1 <= 0; gain2 <= 0;
            invert1 <= 0; invert2 <= 0; valid1 <= 0; valid2 <= 0;
            product <= 0; dac_target <= 0; target_valid <= 0; saturated <= 0;
        end else begin
            phase_reg <= phase_codes;
            gain1 <= gain_shift; invert1 <= invert; valid1 <= phase_valid;
            product <= phase_reg * 18'sd104858;
            gain2 <= gain1; invert2 <= invert1; valid2 <= valid1;
            target_valid <= valid2;
            saturated <= valid2 && (scaled>32767 || scaled < -32768);
            dac_target <= !valid2 ? 16'sd0 : scaled>32767 ? 16'sh7fff :
                          scaled < -32768 ? 16'sh8000 : scaled[15:0];
        end
    end
endmodule
