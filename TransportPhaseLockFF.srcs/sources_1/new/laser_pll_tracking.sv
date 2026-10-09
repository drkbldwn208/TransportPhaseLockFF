`timescale 1ns / 1ps
// Stage 4: preserve the acquired operating point and slew detector sensitivity.
// V = saved_DAC + (unwrapped_phase - saved_phase) * coefficient / 2^26.
// 104858 is the stage-3 gain at shift 0; target shifts 0..8 give 1..256 times it.
// The 24-bit slip memory remains upstream. Only the DAC representation clips.
module laser_pll_tracking (
    input wire clk,
    input wire rst_n,
    input wire arm,
    input wire signed [42:0] phase_codes,
    input wire phase_valid,
    input wire signed [15:0] held_dac,
    input wire [3:0] initial_gain_shift,
    input wire invert,
    input wire [31:0] tracking_control,
    output reg signed [15:0] dac_target,
    output reg target_valid,
    output reg saturated,
    output wire [31:0] tracking_status
);
    reg initialized;
    reg signed [42:0] phase_origin, phase_reg;
    reg signed [15:0] bias_dac;
    reg [25:0] coefficient;
    reg [19:0] ramp_count;
    wire [3:0] target_shift = tracking_control[3:0]>8 ? 4'd8 : tracking_control[3:0];
    wire [3:0] start_shift = initial_gain_shift>8 ? 4'd8 : initial_gain_shift;
    wire [4:0] interval_log2 = tracking_control[8:4]>20 ? 5'd20 : tracking_control[8:4];
    wire [19:0] ramp_mask = (21'd1 << interval_log2)-1'b1;
    wire [25:0] target_coefficient = 26'd104858 << target_shift;
    // Relative step <= 1/256, in either direction; clamp the final step exactly.
    wire [25:0] gain_step = coefficient >> 8;
    wire ramping = initialized && coefficient!=target_coefficient;
    always @(posedge clk) begin
        if (!rst_n || !arm || !phase_valid) begin
            initialized<=0; phase_origin<=0; bias_dac<=0;
            coefficient<=26'd104858; ramp_count<=0;
        end else if (!initialized) begin
            initialized<=1; phase_origin<=phase_codes; bias_dac<=held_dac;
            coefficient<=26'd104858 << start_shift; ramp_count<=0;
        end else if (ramping) begin
            ramp_count<=(ramp_count+1'b1)&ramp_mask;
            if (ramp_count==ramp_mask) begin
                if (coefficient<target_coefficient)
                    coefficient <= target_coefficient-coefficient<=gain_step ?
                                   target_coefficient : coefficient+gain_step;
                else
                    coefficient <= coefficient-target_coefficient<=gain_step ?
                                   target_coefficient : coefficient-gain_step;
            end
        end else ramp_count<=0;
    end

    // Six registers: input, origin subtraction, bound, multiply, round, clip.
    // Register the wide subtraction separately from the DSP multiplier.
    reg signed [43:0] phase_delta;
    reg signed [25:0] limited_phase;
    (* use_dsp = "yes" *) reg signed [51:0] product;
    reg signed [26:0] delta_dac;
    reg [4:0] valid_pipe;
    reg [4:0] invert_pipe;
    wire signed [26:0] rounded = $signed(product[51:26]) + $signed({26'b0,product[25]});
    wire signed [27:0] corrected = $signed(delta_dac) + $signed(bias_dac);
    always @(posedge clk) begin
        if (!rst_n || !arm || !phase_valid) begin
            phase_reg<=0; phase_delta<=0; limited_phase<=0; product<=0;
            delta_dac<=0; valid_pipe<=0; invert_pipe<=0;
            dac_target<=0; target_valid<=0; saturated<=0;
        end else begin
            phase_reg<=phase_codes;
            phase_delta<=$signed({phase_reg[42],phase_reg}) -
                         $signed({phase_origin[42],phase_origin});
            limited_phase<=phase_delta>33554431 ? 26'sh1ffffff :
                           phase_delta < -33554432 ? 26'sh2000000 : phase_delta[25:0];
            product<=limited_phase*$signed(coefficient);
            delta_dac<=invert_pipe[3] ? -rounded : rounded;
            valid_pipe<={valid_pipe[3:0],initialized};
            invert_pipe<={invert_pipe[3:0],invert};
            target_valid<=valid_pipe[4];
            saturated<=valid_pipe[4] && (corrected>32767 || corrected < -32768);
            dac_target<=!valid_pipe[4] ? 16'sd0 : corrected>32767 ? 16'sh7fff :
                        corrected < -32768 ? 16'sh8000 : corrected[15:0];
        end
    end
    assign tracking_status={initialized,ramping,saturated,target_valid,2'b0,coefficient};
endmodule
