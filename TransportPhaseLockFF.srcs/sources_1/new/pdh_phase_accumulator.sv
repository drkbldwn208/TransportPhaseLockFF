`timescale 1ns / 1ps
// FCW units: turns per 3.44064-GS/s sample, with 48 fractional bits.
// One frame is 14 such samples. Frequency changes never reset phase.
module pdh_phase_accumulator #(
    parameter [47:0] RESET_FCW = 48'd98170681051429
)(
    input wire clk, rst_n,
    input wire [47:0] target_fcw,
    output reg [47:0] active_fcw,
    output wire ramping,
    output reg [671:0] sum_phase,
    output reg [383:0] reference_phase
);
    localparam [47:0] SLEW_STEP = 48'd1024;
    reg [47:0] frame_phase, frame_step;
    reg [47:0] sum_offset [0:13];
    reg [47:0] reference_offset [0:7];
    wire increasing = target_fcw > active_fcw;
    wire [47:0] distance = increasing ? target_fcw-active_fcw : active_fcw-target_fcw;
    assign ramping = active_fcw != target_fcw;

    always @(posedge clk) begin
        if (!rst_n) begin
            active_fcw <= RESET_FCW;
            frame_phase <= 0;
            frame_step <= 14*RESET_FCW;
        end else begin
            if (distance <= SLEW_STEP) active_fcw <= target_fcw;
            else if (increasing) active_fcw <= active_fcw + SLEW_STEP;
            else active_fcw <= active_fcw - SLEW_STEP;
            frame_step <= 14*active_fcw;
            frame_phase <= frame_phase + frame_step;
        end
    end

    // Register the constant multiples before adding the common frame phase.
    // All lanes of one output word use the same frequency snapshot.
    for (genvar lane=0; lane<14; lane=lane+1) begin : sum_lane
        always @(posedge clk) begin
            if (!rst_n) sum_offset[lane] <= lane*RESET_FCW;
            else sum_offset[lane] <= lane*active_fcw;
            sum_phase[48*lane+:48] <= frame_phase + sum_offset[lane];
        end
    end
    for (genvar lane=0; lane<8; lane=lane+1) begin : reference_lane
        // 14/8 samples of the main DAC per reference sample. Keep the product
        // wide BEFORE dividing by 8, then wrap to one turn. No phase drift.
        wire [54:0] offset_product = active_fcw * (14*lane);
        localparam [54:0] RESET_PRODUCT = RESET_FCW * (14*lane);
        always @(posedge clk) begin
            if (!rst_n) reference_offset[lane] <= RESET_PRODUCT >> 3;
            else reference_offset[lane] <= offset_product >> 3;
            reference_phase[48*lane+:48] <= frame_phase + reference_offset[lane];
        end
    end
endmodule
