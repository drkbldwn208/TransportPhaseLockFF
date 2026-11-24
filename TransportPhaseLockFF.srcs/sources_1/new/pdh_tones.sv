`timescale 1ns / 1ps
// PDH3: two 48-bit DDSs, direct parallel ROM reads, FCW slew = 1024/clock.
// DAC230/0: Ac*cos(carrier) + Am*cos(modulation), 14 samples/clock.
// DAC228/2: Ar*cos(modulation + reference_phase), 8 samples/clock.
module pdh_tones (
    input wire clk, rst_n, gpio_clk,
    input wire [31:0] control, amplitudes, reference_settings,
    input wire [31:0] carrier_fcw_low, carrier_fcw_high,
    input wire [31:0] modulation_fcw_low, modulation_fcw_high,
    output wire [31:0] status, feature_version,
    output reg [223:0] m_sum_tdata,
    output wire m_sum_tvalid,
    input wire m_sum_tready,
    output reg [127:0] m_ref_tdata,
    output wire m_ref_tvalid,
    input wire m_ref_tready
);
    wire [191:0] settings;
    // One handshake carries all words, including the commit bit. Write both
    // FCW halves and amplitudes first, then toggle control[2]. Intermediate
    // transfers have the OLD commit bit, so no torn 48-bit word is applied.
    gpio_word_cdc #(.WIDTH(192), .INITIAL_WORD(0)) settings_cdc (
        .gpio_clk(gpio_clk), .clk(clk), .pl_word(settings),
        .gpio_word({modulation_fcw_high[15:0],modulation_fcw_low,
                    carrier_fcw_high[15:0],carrier_fcw_low,
                    reference_settings,amplitudes,control})
    );
    wire [31:0] ctrl=settings[31:0], amps=settings[63:32], ref_settings=settings[95:64];
    reg commit_ack, clear_ack, sum_enable, ref_enable;
    reg invalid_config, sum_stalled, ref_stalled, clipped;
    reg signed [15:0] carrier_gain, modulation_gain, reference_gain;
    reg [15:0] reference_phase_offset;
    reg [47:0] carrier_target, modulation_target;
    wire carrier_ramping, modulation_ramping;
    wire [671:0] carrier_phase, modulation_phase;
    wire [383:0] reference_phase;
    wire [47:0] carrier_active, modulation_active;
    wire [16:0] requested_sum={1'b0,amps[15:0]}+{1'b0,amps[31:16]};
    wire bad_amplitudes=amps[15] || amps[31] || requested_sum>17'd32767 || ref_settings[15];
    wire fault=invalid_config || sum_stalled || ref_stalled || clipped;
    wire [21:0] lane_clip;
    assign feature_version=32'h50444803;
    assign status={22'd0,modulation_ramping,carrier_ramping,rst_n,clipped,
                   ref_stalled,sum_stalled,invalid_config,commit_ack,ref_enable,sum_enable};
    assign m_sum_tvalid=rst_n;
    assign m_ref_tvalid=rst_n;

    pdh_phase_accumulator carrier (.clk(clk),.rst_n(rst_n),.target_fcw(carrier_target),
        .active_fcw(carrier_active),.ramping(carrier_ramping),.sum_phase(carrier_phase),.reference_phase());
    pdh_phase_accumulator #(.RESET_FCW(48'd4908534052571)) modulation (
        .clk(clk),.rst_n(rst_n),.target_fcw(modulation_target),.active_fcw(modulation_active),
        .ramping(modulation_ramping),.sum_phase(modulation_phase),.reference_phase(reference_phase));

    always @(posedge clk) begin
        if (!rst_n) begin
            commit_ack<=0; clear_ack<=0; sum_enable<=0; ref_enable<=0;
            carrier_gain<=0; modulation_gain<=0; reference_gain<=0; reference_phase_offset<=0;
            carrier_target<=48'd98170681051429; modulation_target<=48'd4908534052571;
            invalid_config<=0; sum_stalled<=0; ref_stalled<=0; clipped<=0;
        end else begin
            if (ctrl[3]!=clear_ack) begin
                clear_ack<=ctrl[3]; invalid_config<=0; sum_stalled<=0; ref_stalled<=0; clipped<=0;
            end
            if (ctrl[2]!=commit_ack) begin
                commit_ack<=ctrl[2];
                if (bad_amplitudes) begin
                    invalid_config<=1; sum_enable<=0; ref_enable<=0;
                end else begin
                    carrier_gain<=amps[15:0]; modulation_gain<=amps[31:16];
                    reference_gain<=ref_settings[15:0]; reference_phase_offset<=ref_settings[31:16];
                    carrier_target<=settings[143:96]; modulation_target<=settings[191:144];
                    sum_enable<=ctrl[0]; ref_enable<=ctrl[1];
                end
            end
            // Oscillators always run. A DAC stall mutes BOTH outputs rather
            // than stopping one clock sequence and losing their coherence.
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

    // ROM address -> ROM read -> quadrant sign -> DSP -> sum/round -> output.
    // One dual-port ROM serves carrier+modulation for each of the 14 lanes.
    for (genvar lane=0; lane<14; lane=lane+1) begin : sum_lane
        wire signed [15:0] c, m;
        pdh_cosine_pair lut (.clk(clk),.phase_a(carrier_phase[48*lane+34+:14]),
            .phase_b(modulation_phase[48*lane+34+:14]),.cosine_a(c),.cosine_b(m));
        (* use_dsp="yes" *) reg signed [31:0] product_carrier, product_modulation;
        reg signed [32:0] rounded;
        assign lane_clip[lane]=sum_enable && !fault &&
            (rounded>33'sd1073741823 || rounded< -33'sd1073741824);
        always @(posedge clk) begin
            product_carrier<=c*carrier_gain;
            product_modulation<=m*modulation_gain;
            rounded<=$signed({product_carrier[31],product_carrier})+
                     $signed({product_modulation[31],product_modulation})+33'sd16384;
            if (!rst_n) m_sum_tdata[16*lane+:16]<=0;
            else if (m_sum_tready) m_sum_tdata[16*lane+:16]<=sum_enable && !fault ? rounded_code(rounded) : 16'd0;
        end
    end
    // Two reference samples per ROM. Phase is added before lookup, so a 180
    // degree adjustment gives the same amplitude with the opposite sign.
    wire signed [15:0] ref_cosine [0:7];
    for (genvar pair=0; pair<4; pair=pair+1) begin : ref_pair
        wire [15:0] phase_a=reference_phase[96*pair+32+:16]+reference_phase_offset;
        wire [15:0] phase_b=reference_phase[96*pair+80+:16]+reference_phase_offset;
        pdh_cosine_pair lut (.clk(clk),.phase_a(phase_a[15:2]),.phase_b(phase_b[15:2]),
            .cosine_a(ref_cosine[2*pair]),.cosine_b(ref_cosine[2*pair+1]));
    end
    for (genvar lane=0; lane<8; lane=lane+1) begin : ref_lane
        (* use_dsp="yes" *) reg signed [31:0] product;
        reg signed [32:0] rounded;
        assign lane_clip[lane+14]=ref_enable && !fault &&
            (rounded>33'sd1073741823 || rounded< -33'sd1073741824);
        always @(posedge clk) begin
            product<=ref_cosine[lane]*reference_gain;
            rounded<=$signed({product[31],product})+33'sd16384;
            if (!rst_n) m_ref_tdata[16*lane+:16]<=0;
            else if (m_ref_tready) m_ref_tdata[16*lane+:16]<=ref_enable && !fault ? rounded_code(rounded) : 16'd0;
        end
    end
endmodule
