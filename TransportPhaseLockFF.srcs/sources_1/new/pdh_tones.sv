`timescale 1ns / 1ps
// DAC229/2: I=(Ac+As)cos(570 MHz t), Q=(Ac-As)sin(570 MHz t).
// The existing RFDC C2R mixer at +630 MHz produces Ac*cos(1.2 GHz t)
// + As*cos(60 MHz t). DAC228/2 is the coherent 60 MHz reference.
// No run-time divisions, NCO truncation, or changes to RFDC bus/sample rates.
module pdh_tones (
    input wire clk, rst_n,
    input wire [31:0] control, amplitudes, reference_coefficients,
    output wire [31:0] status, feature_version,
    output reg [223:0] m_sum_tdata,
    output wire m_sum_tvalid,
    input wire m_sum_tready,
    output reg [127:0] m_ref_tdata,
    output wire m_ref_tvalid,
    input wire m_ref_tready
);
    reg [9:0] frame;
    reg commit_ack, clear_ack, sum_enable, ref_enable;
    reg invalid_config, sum_stalled, ref_stalled, clipped;
    reg signed [15:0] sum_gain, difference_gain, ref_cos_gain, ref_sin_gain;
    wire [16:0] requested_sum={1'b0,amplitudes[15:0]}+{1'b0,amplitudes[31:16]};
    wire bad_amplitudes=amplitudes[15] || amplitudes[31] || requested_sum>17'd32767;
    wire fault=invalid_config || sum_stalled || ref_stalled || clipped;
    wire [14:0] lane_clip;
    assign feature_version=32'h50444801; // PDH, register layout 1
    assign status={24'd0,rst_n,clipped,ref_stalled,sum_stalled,invalid_config,commit_ack,ref_enable,sum_enable};
    assign m_sum_tvalid=rst_n;
    assign m_ref_tvalid=rst_n;

    // GPIOs use this same fabric clock. Write all coefficient words, then toggle
    // control[2]: all gains and enables take effect together, without phase reset.
    // control[3] toggles to clear sticky faults. Frame time always runs.
    always @(posedge clk) begin
        if (!rst_n) begin
            frame<=0; commit_ack<=0; clear_ack<=0; sum_enable<=0; ref_enable<=0;
            sum_gain<=0; difference_gain<=0; ref_cos_gain<=0; ref_sin_gain<=0;
            invalid_config<=0; sum_stalled<=0; ref_stalled<=0; clipped<=0;
        end else begin
            frame<=frame+1'b1;
            if (control[3]!=clear_ack) begin
                clear_ack<=control[3]; invalid_config<=0; sum_stalled<=0; ref_stalled<=0; clipped<=0;
            end
            if (control[2]!=commit_ack) begin
                commit_ack<=control[2];
                if (bad_amplitudes) begin
                    invalid_config<=1; sum_enable<=0; ref_enable<=0;
                end else begin
                    sum_gain<=requested_sum[15:0];
                    difference_gain<=$signed(amplitudes[15:0])-$signed(amplitudes[31:16]);
                    ref_cos_gain<=reference_coefficients[15:0];
                    ref_sin_gain<=reference_coefficients[31:16];
                    sum_enable<=control[0]; ref_enable<=control[1];
                end
            end
            // Never pause one oscillator relative to the other. A streaming gap
            // mutes both outputs and is reported; reconfigure before using PDH.
            if (sum_enable && !m_sum_tready) sum_stalled<=1;
            if (ref_enable && !m_ref_tready) ref_stalled<=1;
            if (|lane_clip) clipped<=1;
        end
    end

    function automatic [15:0] rounded_code(input signed [32:0] value);
        if (value>33'sd1073741823) rounded_code=16'h7fff;
        else if (value< -33'sd1073741824) rounded_code=16'h8000;
        else rounded_code=value >>> 15;
    endfunction

    // Pipeline: synchronous ROM -> DSP multiply -> sum/round -> AXIS output.
    // ROM angle is the actual time of each lane, not a repeated scalar sample.
    for (genvar lane=0;lane<7;lane=lane+1) begin : sum_lane
        (* rom_style="block" *) reg [31:0] rom[0:1023];
        initial $readmemh($sformatf("pdh_offset_%0d.mem",lane),rom);
        reg [31:0] wave;
        (* use_dsp="yes" *) reg signed [31:0] product_i, product_q;
        reg signed [32:0] rounded_i, rounded_q;
        assign lane_clip[lane]=sum_enable && !fault &&
            (rounded_i>33'sd1073741823 || rounded_i< -33'sd1073741824 ||
             rounded_q>33'sd1073741823 || rounded_q< -33'sd1073741824);
        always @(posedge clk) begin
            wave<=rom[frame];
            product_i<=$signed(wave[15:0])*sum_gain;
            product_q<=$signed(wave[31:16])*difference_gain;
            rounded_i<=$signed(product_i)+33'sd16384;
            rounded_q<=$signed(product_q)+33'sd16384;
            if (!rst_n) m_sum_tdata[32*lane+:32]<=0;
            else if (m_sum_tready) m_sum_tdata[32*lane+:32]<=sum_enable && !fault ?
                {rounded_code(rounded_q),rounded_code(rounded_i)} : 32'd0;
        end
    end
    for (genvar lane=0;lane<8;lane=lane+1) begin : ref_lane
        (* rom_style="block" *) reg [31:0] rom[0:511];
        initial $readmemh($sformatf("pdh_reference_%0d.mem",lane),rom);
        reg [31:0] wave;
        (* use_dsp="yes" *) reg signed [31:0] product_cos, product_sin;
        reg signed [32:0] rounded;
        assign lane_clip[lane+7]=ref_enable && !fault &&
            (rounded>33'sd1073741823 || rounded< -33'sd1073741824);
        always @(posedge clk) begin
            wave<=rom[frame[8:0]];
            product_cos<=$signed(wave[15:0])*ref_cos_gain;
            product_sin<=$signed(wave[31:16])*ref_sin_gain;
            rounded<=$signed({product_cos[31],product_cos})+
                     $signed({product_sin[31],product_sin})+33'sd16384;
            if (!rst_n) m_ref_tdata[16*lane+:16]<=0;
            else if (m_ref_tready) m_ref_tdata[16*lane+:16]<=ref_enable && !fault ? rounded_code(rounded) : 16'd0;
        end
    end
endmodule
