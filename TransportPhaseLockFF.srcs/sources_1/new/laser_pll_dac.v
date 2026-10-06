`timescale 1ns / 1ps
// One independent error sample/clock, repeated into the RFDC's seven IQ pairs.
// DAC 229/1 must use C2R with a zero-frequency, zero-phase mixer.
module laser_pll_dac (
    input wire clk,
    input wire rst_n,
    input wire enable,
    input wire clear,
    input wire signed [15:0] dac_target,
    input wire target_valid,
    input wire target_saturated,
    output wire [223:0] m_axis_tdata,
    output wire m_axis_tvalid,
    input wire m_axis_tready,
    output reg saturated,
    output reg stalled
);
    reg signed [15:0] dac_code;
    always @(posedge clk) begin
        if (!rst_n || !enable || clear) begin
            saturated <= 0;
            stalled <= 0;
        end else begin
            if (!m_axis_tready) stalled <= 1;
            if (m_axis_tready) saturated <= target_valid && target_saturated;
        end
        // Keep an unaccepted beat stable. Discard intermediate errors instead
        // of buffering them; stall is a fault indication, not normal operation.
        if (!rst_n) dac_code <= 0;
        else if (m_axis_tready)
            dac_code <= (!enable || clear || !target_valid) ? 16'sd0 : dac_target;
    end
    genvar lane;
    generate for (lane=0; lane<7; lane=lane+1) begin : pack
        assign m_axis_tdata[32*lane +: 32] = {16'b0,dac_code};
    end endgenerate
    assign m_axis_tvalid = rst_n;
endmodule
