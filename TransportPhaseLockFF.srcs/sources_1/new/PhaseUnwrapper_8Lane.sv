`timescale 1ns / 1ps

module PhaseUnwrapper_8Lane #(
    parameter int IN_WIDTH = 12,
    parameter int OUT_WIDTH = 20,
    parameter int WRAP_THRESHOLD = 500
)(
    input  logic clk,
    input  logic rst_n,
    input  logic [IN_WIDTH*8-1:0] phase_1_in,   // slow ref
    input  logic [IN_WIDTH*8-1:0] phase_2_in,   // fast 2x signal
    input  logic unwrap_en,
    output logic [OUT_WIDTH*8-1:0] error_signal_out
);

    logic signed [IN_WIDTH-1:0] p1_reg [7:0];
    logic signed [IN_WIDTH-1:0] p2_reg [7:0];

    logic signed [11:0] E_wrapped [7:0];
    logic signed [11:0] E_wrapped_prev7;
    logic        [9:0]  diff_10 [7:0];

    logic signed [12:0] delta [7:0];
    logic signed [1:0]  slip  [7:0];

    logic signed [2:0]  cs1 [7:0];
    logic signed [3:0]  cs2 [7:0];
    logic signed [4:0]  cs3 [7:0];

    logic signed [9:0]  global_wrap;
    logic signed [9:0]  total_wrap [7:0];

    logic signed [11:0] E_dly1 [7:0], E_dly2 [7:0], E_dly3 [7:0], E_dly4 [7:0], E_dly5 [7:0], E_dly6 [7:0];

    logic signed [OUT_WIDTH*8-1:0] error_out_reg;

    // 2:1 phase comparator: (2*phase_1 - phase_2) mod 1024, free wrap via 10-bit modular sub
    always_comb begin
        for (int i = 0; i < 8; i++) begin
            diff_10[i] = {p1_reg[i][8:0], 1'b0} - p2_reg[i][9:0];
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            E_wrapped_prev7 <= '0;
            global_wrap <= '0;
            error_out_reg <= '0;
            for (int i = 0; i < 8; i++) begin
                p1_reg[i] <= '0;  p2_reg[i] <= '0;
                E_wrapped[i] <= '0;
                delta[i] <= '0;   slip[i] <= '0;
                cs1[i] <= '0; cs2[i] <= '0; cs3[i] <= '0;
                total_wrap[i] <= '0;
                E_dly1[i] <= '0; E_dly2[i] <= '0; E_dly3[i] <= '0; E_dly4[i] <= '0; E_dly5[i] <= '0; E_dly6[i] <= '0;
            end
        end else begin
            // Stage 1: register inputs, build wrapped 2:1 error
            for (int i = 0; i < 8; i++) begin
                p1_reg[i]    <= phase_1_in[i*IN_WIDTH +: IN_WIDTH];
                p2_reg[i]    <= phase_2_in[i*IN_WIDTH +: IN_WIDTH];
                E_wrapped[i] <= { {2{diff_10[i][9]}}, diff_10[i] };
            end
            E_wrapped_prev7 <= E_wrapped[7];

            // Stage 2: inter-sample delta
            delta[0] <= E_wrapped[0] - E_wrapped_prev7;
            for (int i = 1; i < 8; i++)
                delta[i] <= E_wrapped[i] - E_wrapped[i-1];

            // Slip detection + delay line (BUGFIX: E_dly1 unconditional)
            for (int i = 0; i < 8; i++) begin
                E_dly1[i] <= E_wrapped[i];
                if (unwrap_en) begin
                    if      (delta[i] < -WRAP_THRESHOLD) slip[i] <=  2'sd1;
                    else if (delta[i] >  WRAP_THRESHOLD) slip[i] <= -2'sd1;
                    else                                 slip[i] <=  2'sd0;
                end else begin
                    slip[i] <= 2'sd0;
                end
            end

            // Stage 3: pairwise sums
            cs1[0] <= slip[0];                cs1[1] <= slip[0] + slip[1];
            cs1[2] <= slip[2];                cs1[3] <= slip[2] + slip[3];
            cs1[4] <= slip[4];                cs1[5] <= slip[4] + slip[5];
            cs1[6] <= slip[6];                cs1[7] <= slip[6] + slip[7];
            for (int i = 0; i < 8; i++) E_dly2[i] <= E_dly1[i];

            // Stage 4
            cs2[0] <= cs1[0];                 cs2[1] <= cs1[1];
            cs2[2] <= cs1[1] + cs1[2];        cs2[3] <= cs1[1] + cs1[3];
            cs2[4] <= cs1[4];                 cs2[5] <= cs1[5];
            cs2[6] <= cs1[5] + cs1[6];        cs2[7] <= cs1[5] + cs1[7];
            for (int i = 0; i < 8; i++) E_dly3[i] <= E_dly2[i];

            // Stage 5: per-lane prefix sum within cycle
            cs3[0] <= cs2[0];                 cs3[1] <= cs2[1];
            cs3[2] <= cs2[2];                 cs3[3] <= cs2[3];
            cs3[4] <= cs2[3] + cs2[4];        cs3[5] <= cs2[3] + cs2[5];
            cs3[6] <= cs2[3] + cs2[6];        cs3[7] <= cs2[3] + cs2[7];
            for (int i = 0; i < 8; i++) E_dly4[i] <= E_dly3[i];

            // Stage 6: global accumulator + per-lane total
            if (!unwrap_en) begin
                global_wrap <= '0;
                for (int i = 0; i < 8; i++) begin
                    total_wrap[i] <= '0;
                    E_dly5[i]     <= E_dly4[i];
                    E_dly6[i] <= E_dly5[i];
                end
            end else begin
                global_wrap <= global_wrap + cs3[7];
                for (int i = 0; i < 8; i++) begin
                    total_wrap[i] <= global_wrap + cs3[i];
                    E_dly5[i]     <= E_dly4[i];
                    E_dly6[i] <= E_dly5[i];
                end
            end
            
            // Stage 7: unwrapped output, explicit sign-extension
            for (int i = 0; i < 8; i++) begin
                error_out_reg[i*OUT_WIDTH +: OUT_WIDTH] <=
                    OUT_WIDTH'(signed'(E_dly6[i])) +
                    (OUT_WIDTH'(signed'(total_wrap[i])) <<< 10);
            end
        end
    end

    assign error_signal_out = error_out_reg;

endmodule