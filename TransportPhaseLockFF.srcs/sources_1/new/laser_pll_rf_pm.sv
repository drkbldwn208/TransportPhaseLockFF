`timescale 1ns / 1ps
// Constant-envelope I/Q for DAC229/2's existing RFDC C2R carrier NCO.
// Input phase units: 2^18/turn. Use the existing quarter-wave ROM (16-bit
// phase addresses, midpoint samples). applied_phase accompanies the actual
// AXIS word, so the FRA divides out this source pipeline's latency.
module laser_pll_rf_pm (
    input wire clk, rst_n,
    input wire signed [19:0] phase_command,
    input wire [15:0] amplitude,
    output wire [223:0] m_axis_tdata,
    output wire m_axis_tvalid,
    input wire m_axis_tready,
    output reg signed [17:0] applied_phase
);
    wire signed [20:0] rounded_phase = $signed(phase_command)+21'sd2;
    wire [15:0] phase_index = rounded_phase[17:2];
    wire [15:0] cosine_index = phase_index+16'h4000;
    wire [13:0] sin_address = phase_index[14] ? ~phase_index[13:0] : phase_index[13:0];
    wire [13:0] cos_address = cosine_index[14] ? ~cosine_index[13:0] : cosine_index[13:0];
    (* rom_style="block" *) reg [17:0] sine_rom[0:16383];
    initial $readmemh("laser_pll_sine.mem",sine_rom);
    reg [17:0] sin_magnitude, cos_magnitude;
    reg sin_negative, cos_negative;
    reg signed [17:0] sine, cosine;
    reg [15:0] amp1, amp2, amp3;
    reg signed [17:0] phase1, phase2, phase3;
    (* use_dsp="yes" *) reg signed [34:0] product_i, product_q;
    reg signed [15:0] output_i, output_q;
    // With ready low, the accepted-output record stays stable; internal
    // time still advances. The FRA flags a stall instead of hiding lost samples.
    always @(posedge clk) begin
        sin_magnitude<=sine_rom[sin_address];
        cos_magnitude<=sine_rom[cos_address];
        sin_negative<=phase_index[15]; cos_negative<=cosine_index[15];
        phase1<=phase_index==0 ? 18'sd0 : {phase_index,2'b10};
        amp1<=amplitude[15] ? 16'd32767 : amplitude;
        sine<=sin_negative ? -$signed(sin_magnitude) : $signed(sin_magnitude);
        cosine<=cos_negative ? -$signed(cos_magnitude) : $signed(cos_magnitude);
        phase2<=phase1; amp2<=amp1;
        product_i<=cosine*$signed({1'b0,amp2});
        product_q<=sine*$signed({1'b0,amp2});
        phase3<=phase2; amp3<=amp2;
        if (!rst_n) begin output_i<=0; output_q<=0; applied_phase<=0; end
        else if (m_axis_tready) begin
            // Exactly reproduce the old I=32767,Q=0 source with zero PM.
            output_i<=phase3==0 ? $signed(amp3) : (product_i+35'sd65536) >>> 17;
            output_q<=phase3==0 ? 16'sd0 : (product_q+35'sd65536) >>> 17;
            applied_phase<=phase3;
        end
    end
    for (genvar lane=0; lane<7; lane=lane+1) begin : pack
        assign m_axis_tdata[32*lane+:32]={output_q,output_i};
    end
    assign m_axis_tvalid=rst_n;
endmodule
