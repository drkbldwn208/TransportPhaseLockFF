`timescale 1ns / 1ps
// Candidate datapath. Coefficients must match the phase word at these inputs.
// CORDIC outputs are signed Q22 (24 bits). Coefficients are DAC counts * 4,
// signed 18 bits; amplitude is already folded into each rotation coefficient.
module pdh_parallel_rotations (
    input wire clk, rst_n, valid,
    input wire [1:0] enable,
    input wire signed [23:0] carrier_cos, carrier_sin,
    input wire signed [23:0] modulation_cos, modulation_sin,
    input wire [1295:0] coefficients,
    input wire fault,
    output reg [223:0] sum_data,
    output reg [127:0] reference_data,
    input wire sum_ready, reference_ready,
    output wire clipped, stalled
);
    reg [2:0] valid_pipe;
    reg [1:0] enable_pipe[0:2];
    wire [21:0] clip_lane;
    assign clipped=|clip_lane;
    assign stalled=valid_pipe[2] &&
        ((enable_pipe[2][0] && !sum_ready) || (enable_pipe[2][1] && !reference_ready));

    always @(posedge clk) begin
        if (!rst_n) begin
            valid_pipe<=0;
            for (integer k=0;k<3;k=k+1) enable_pipe[k]<=0;
        end else begin
            valid_pipe<={valid_pipe[1:0],valid};
            enable_pipe[0]<=enable;
            enable_pipe[1]<=enable_pipe[0];
            enable_pipe[2]<=enable_pipe[1];
        end
    end

    function automatic [15:0] saturated_code(input signed [43:0] rounded);
        if ((rounded >>> 24)>32767) saturated_code=16'h7fff;
        else if ((rounded >>> 24)<-32768) saturated_code=16'h8000;
        else saturated_code=rounded >>> 24;
    endfunction

    for (genvar lane=0;lane<14;lane=lane+1) begin : sum_lane
        (* use_dsp="yes" *) reg signed [41:0] cc, cs, mc, ms;
        reg signed [42:0] carrier, modulation;
        reg signed [43:0] summed;
        wire signed [43:0] rounded=summed+44'sd8388608;
        assign clip_lane[lane]=valid_pipe[2] && enable_pipe[2][0] &&
            (((rounded >>> 24)>32767) || ((rounded >>> 24)<-32768));
        always @(posedge clk) begin
            cc<=carrier_cos*$signed(coefficients[(2*lane)*18+:18]);
            cs<=carrier_sin*$signed(coefficients[(2*lane+1)*18+:18]);
            mc<=modulation_cos*$signed(coefficients[(28+2*lane)*18+:18]);
            ms<=modulation_sin*$signed(coefficients[(29+2*lane)*18+:18]);
            carrier<=$signed({cc[41],cc})+$signed({cs[41],cs});
            modulation<=$signed({mc[41],mc})+$signed({ms[41],ms});
            summed<=$signed({carrier[42],carrier})+$signed({modulation[42],modulation});
            if (!rst_n) sum_data[lane*16+:16]<=0;
            else if (sum_ready)
                sum_data[lane*16+:16]<=valid_pipe[2] && enable_pipe[2][0] && !fault ?
                    saturated_code(rounded) : 16'd0;
        end
    end
    for (genvar lane=0;lane<8;lane=lane+1) begin : reference_lane
        (* use_dsp="yes" *) reg signed [41:0] rc, rs;
        reg signed [42:0] rotated;
        reg signed [43:0] delayed;
        wire signed [43:0] rounded=delayed+44'sd8388608;
        assign clip_lane[14+lane]=valid_pipe[2] && enable_pipe[2][1] &&
            (((rounded >>> 24)>32767) || ((rounded >>> 24)<-32768));
        always @(posedge clk) begin
            rc<=modulation_cos*$signed(coefficients[(56+2*lane)*18+:18]);
            rs<=modulation_sin*$signed(coefficients[(57+2*lane)*18+:18]);
            rotated<=$signed({rc[41],rc})+$signed({rs[41],rs});
            delayed<=$signed({rotated[42],rotated}); // Align with summed DAC path.
            if (!rst_n) reference_data[lane*16+:16]<=0;
            else if (reference_ready)
                reference_data[lane*16+:16]<=valid_pipe[2] && enable_pipe[2][1] && !fault ?
                    saturated_code(rounded) : 16'd0;
        end
    end
endmodule
