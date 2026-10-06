`timescale 1ns / 1ps
// atan2(Q,I), full circle. Three vectoring iterations per pipeline stage.
// Output: signed binary turns, -131072 = -pi, 65536 = pi/2.
module laser_pll_cordic (
    input wire clk,
    input wire rst_n,
    input wire signed [23:0] i_sample,
    input wire signed [23:0] q_sample,
    input wire sample_valid,
    output wire signed [17:0] phase,
    output wire phase_valid
);
    function automatic signed [23:0] angle(input integer k);
        case (k)
            0: angle=2097152; 1: angle=1238021; 2: angle=654136;
            3: angle=332050; 4: angle=166669; 5: angle=83416;
            6: angle=41718; 7: angle=20860; 8: angle=10430;
            9: angle=5215; 10: angle=2608; 11: angle=1304;
            12: angle=652; 13: angle=326; 14: angle=163;
            15: angle=81; 16: angle=41; 17: angle=20;
            default: angle=0;
        endcase
    endfunction
    reg signed [25:0] x [0:6];
    reg signed [25:0] y [0:6];
    reg signed [23:0] z [0:6];
    reg [6:0] valid_pipe;
    wire signed [25:0] wide_i = {{2{i_sample[23]}}, i_sample};
    wire signed [25:0] wide_q = {{2{q_sample[23]}}, q_sample};
    always @(posedge clk) begin
        // Rotate the left half plane by pi; binary-turn arithmetic wraps exactly.
        x[0] <= i_sample[23] ? -wide_i : wide_i;
        y[0] <= i_sample[23] ? -wide_q : wide_q;
        z[0] <= i_sample[23] ? 24'sh800000 : 0;
        if (!rst_n) valid_pipe <= 0;
        else valid_pipe <= {valid_pipe[5:0], sample_valid};
    end
    for (genvar s = 0; s < 6; s = s + 1) begin : stages
        localparam integer K = 3*s;
        wire signed [25:0] xa = y[s][25] ? x[s] - (y[s] >>> K) : x[s] + (y[s] >>> K);
        wire signed [25:0] ya = y[s][25] ? y[s] + (x[s] >>> K) : y[s] - (x[s] >>> K);
        wire signed [23:0] za = y[s][25] ? z[s] - angle(K) : z[s] + angle(K);
        wire signed [25:0] xb = ya[25] ? xa - (ya >>> (K+1)) : xa + (ya >>> (K+1));
        wire signed [25:0] yb = ya[25] ? ya + (xa >>> (K+1)) : ya - (xa >>> (K+1));
        wire signed [23:0] zb = ya[25] ? za - angle(K+1) : za + angle(K+1);
        always @(posedge clk) begin
            x[s+1] <= yb[25] ? xb - (yb >>> (K+2)) : xb + (yb >>> (K+2));
            y[s+1] <= yb[25] ? yb + (xb >>> (K+2)) : yb - (xb >>> (K+2));
            z[s+1] <= yb[25] ? zb - angle(K+2) : zb + angle(K+2);
        end
    end
    wire [23:0] rounded_phase = z[6] + 24'd32;
    assign phase = rounded_phase[23:6];
    assign phase_valid = valid_pipe[6];
endmodule
