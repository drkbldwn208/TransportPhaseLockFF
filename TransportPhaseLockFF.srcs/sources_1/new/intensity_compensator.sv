`timescale 1ns / 1ps
// Feedback only, in common optical-power codes. Root datapath adds feedforward
// and applies ONE incident-power gain to their sum before the actuator lookup.
// PI/PII/PIII mean Kp * product(1 + wi_j/s), with 1/2/3 integral factors.
// The proportional path always runs at 245.76 MHz; integrals update at 122.88 MHz.
// error/output: signed 26-bit codes with 8 fractional bits; state: Q17.32.
// kp and leadlag high-frequency gain: signed Q6.12. Integral alpha: unsigned
// Q0.24 (20-bit storage), approximately 2*pi*f_integral/122.88e6.
// Select order/coefficients only while disabled. Root owns atomic register commit.
module intensity_compensator (
    input wire clk, rst_n, enable, state_reset, hold, input_valid,
    input wire signed [25:0] error_q8,
    input wire [1:0] order,
    input wire signed [17:0] kp_q12,
    input wire [19:0] alpha1_q24, alpha2_q24, alpha3_q24,
    input wire leadlag_enable,
    input wire [31:0] leadlag_alpha_q30,
    input wire signed [17:0] leadlag_gain_q12,
    input wire rail_high, rail_low,
    output wire signed [25:0] feedback_q8,
    output wire output_valid, saturated,
    output wire [31:0] status
);
    localparam signed [50:0] STATE_MAX = 51'sd562949953421311;
    localparam signed [50:0] STATE_MIN = -51'sd562949953421312;
    localparam signed [29:0] SIGNAL_MAX = 30'sd33554431;
    localparam signed [29:0] SIGNAL_MIN = -30'sd33554432;
    reg signed [49:0] integral1, integral2, integral3;
    reg phase;
    reg signed [46:0] increment1, increment2, increment3;
    reg signed [25:0] input1_d, input2_d, input3_d;
    reg input_hold_d;
    reg sample_hold;
    reg state_clip;

    function automatic signed [25:0] limit_signal(input signed [29:0] x);
        begin
            limit_signal=x>SIGNAL_MAX ? 26'sh1ffffff :
                         x<SIGNAL_MIN ? 26'sh2000000 : x[25:0];
        end
    endfunction
    function automatic signed [25:0] state_signal(input signed [49:0] x);
        reg signed [50:0] rounded;
        reg signed [29:0] scaled;
        begin
            rounded=$signed(x)+51'sd8388608;
            scaled=rounded >>> 24;
            state_signal=limit_signal(scaled);
        end
    endfunction
    function automatic signed [49:0] limit_state(input signed [50:0] x);
        begin
            limit_state=x>STATE_MAX ? 50'sh1ffffffffffff :
                        x<STATE_MIN ? 50'sh2000000000000 : x[49:0];
        end
    endfunction

    // Kp precedes the PI factors, so all stored integrals use output-power
    // units. A small Kp therefore does not reduce their available DC range.
    (* use_dsp="yes" *) reg signed [43:0] p_product;
    reg p_valid;
    reg signed [25:0] p_output;
    reg p_output_valid, p_clip;
    wire signed [44:0] p_round=$signed(p_product)+45'sd2048;
    wire signed [32:0] p_scaled=p_round >>> 12;
    wire p_gain_clip=p_scaled>33554431 || p_scaled < -33554432;
    wire signed [25:0] gained_error=p_scaled>33554431 ? 26'sh1ffffff :
                      p_scaled < -33554432 ? 26'sh2000000 : p_scaled[25:0];
    wire signed [25:0] i1_q8=state_signal(integral1);
    wire signed [25:0] i2_q8=state_signal(integral2);
    wire signed [25:0] i3_q8=state_signal(integral3);
    reg signed [25:0] i1_d;
    reg signed [29:0] i12_sum, i_selected_sum;
    wire signed [29:0] x0=$signed(gained_error);
    wire signed [29:0] x1=x0+$signed(i1_d);
    wire signed [29:0] x2=x0+i12_sum;
    wire signed [29:0] chosen=x0+i_selected_sum;
    wire signed [25:0] input1=limit_signal(x0);
    wire signed [25:0] input2=limit_signal(x1);
    wire signed [25:0] input3=limit_signal(x2);
    wire input_clip=chosen>SIGNAL_MAX || chosen<SIGNAL_MIN;
    wire signed [50:0] next1=$signed(integral1)+$signed(increment1);
    wire signed [50:0] next2=$signed(integral2)+$signed(increment2);
    wire signed [50:0] next3=$signed(integral3)+$signed(increment3);

    // Kp has already set the actuator direction. Permit increments that move
    // a railed output back into range; freeze those
    // that drive it further out. Individual state clamps prevent hidden windup.
    wire push1_high=increment1>0;
    wire push2_high=increment2>0;
    wire push3_high=increment3>0;
    wire push1_low=(increment1!=0) && !push1_high;
    wire push2_low=(increment2!=0) && !push2_high;
    wire push3_low=(increment3!=0) && !push3_high;
    wire integrate1=!sample_hold && !hold && kp_q12!=0 &&
                    !(rail_high && push1_high) && !(rail_low && push1_low);
    wire integrate2=!sample_hold && !hold && kp_q12!=0 &&
                    !(rail_high && push2_high) && !(rail_low && push2_low);
    wire integrate3=!sample_hold && !hold && kp_q12!=0 &&
                    !(rail_high && push3_high) && !(rail_low && push3_low);

    always @(posedge clk) begin
        if (!rst_n || !enable || state_reset || !input_valid) begin
            integral1<=0; integral2<=0; integral3<=0; phase<=0;
            increment1<=0; increment2<=0; increment3<=0; sample_hold<=0;
            input1_d<=0; input2_d<=0; input3_d<=0; input_hold_d<=0;
            i1_d<=0; i12_sum<=0; i_selected_sum<=0;
            state_clip<=0; p_product<=0; p_valid<=0;
            p_output<=0; p_output_valid<=0; p_clip<=0;
        end else begin
            phase<=~phase;
            // Integral sums change slowly. Register them on the side path so
            // the proportional signal crosses only one adder and one limiter.
            i1_d<=i1_q8; i12_sum<=$signed(i1_q8)+$signed(i2_q8);
            i_selected_sum<=$signed(i1_q8)+
                (order>=2 ? $signed(i2_q8) : 30'sd0)+
                (order==3 ? $signed(i3_q8) : 30'sd0);
            // Separate the cascaded additions from DSP multiplication. This
            // adds one clock only to the integral drives, not the P path.
            input1_d<=input1; input2_d<=input2; input3_d<=input3; input_hold_d<=hold;
            p_product<=error_q8*kp_q12;
            p_valid<=1;
            p_output<=limit_signal(chosen);
            p_output_valid<=p_valid;
            p_clip<=input_clip || p_gain_clip;
            if (!phase) begin
                increment1<=input1_d*$signed({1'b0,alpha1_q24});
                increment2<=input2_d*$signed({1'b0,alpha2_q24});
                increment3<=input3_d*$signed({1'b0,alpha3_q24});
                sample_hold<=hold || input_hold_d;
            end else begin
                if (integrate1) integral1<=limit_state(next1);
                if (order>=2 && integrate2) integral2<=limit_state(next2);
                if (order==3 && integrate3) integral3<=limit_state(next3);
                state_clip<=(integrate1 && (next1>STATE_MAX || next1<STATE_MIN)) ||
                    (order>=2 && integrate2 && (next2>STATE_MAX || next2<STATE_MIN)) ||
                    (order==3 && integrate3 && (next3>STATE_MAX || next3<STATE_MIN));
            end
            if (order<2) integral2<=0;
            if (order!=3) integral3<=0;
        end
    end

    wire signed [25:0] lag_output;
    wire lag_valid, lag_clip;
    intensity_feedback_leadlag leadlag (
        .clk(clk),.rst_n(rst_n),.reset(state_reset || !enable || !input_valid),
        .input_q8(p_output),.input_valid(p_output_valid),
        .alpha_q30(leadlag_alpha_q30),.gain_q12(leadlag_gain_q12),
        .output_q8(lag_output),.output_valid(lag_valid),.saturated(lag_clip));
    assign feedback_q8=leadlag_enable ? lag_output : p_output;
    assign output_valid=leadlag_enable ? lag_valid : p_output_valid;
    assign saturated=state_clip || p_clip || (leadlag_enable && lag_clip);
    assign status={24'b0,phase,hold,rail_low,rail_high,leadlag_enable,state_clip,p_clip,output_valid};
endmodule

// Unity-DC first-order shelf: z' = z + alpha*(x-z), y = x+(g_inf-1)*(x-z).
// H(s) ~= (1+s/w_zero)/(1+s/w_pole), g_inf=w_pole/w_zero.
// alpha=1-exp(-w_pole/122.88e6), unsigned Q2.30 restricted to 0..1.
// The state update is at half rate; direct feedthrough runs at full rate.
module intensity_feedback_leadlag (
    input wire clk,rst_n,reset,input_valid,
    input wire signed [25:0] input_q8,
    input wire [31:0] alpha_q30,
    input wire signed [17:0] gain_q12,
    output reg signed [25:0] output_q8,
    output reg output_valid,saturated
);
    reg signed [49:0] state;
    reg phase,valid_d;
    (* use_dsp="yes" *) reg signed [59:0] state_product;
    (* use_dsp="yes" *) reg signed [45:0] shelf_product;
    reg signed [25:0] input_d;
    wire [31:0] alpha_safe=alpha_q30>32'd1073741824 ? 32'd1073741824 : alpha_q30;
    wire signed [50:0] state_round=$signed(state)+51'sd8388608;
    wire signed [26:0] state_q8=state_round >>> 24;
    wire signed [26:0] difference=$signed(input_q8)-$signed(state_q8);
    wire signed [18:0] gain_delta=$signed(gain_q12)-19'sd4096;
    wire signed [53:0] state_delta=state_product >>> 6;
    wire signed [54:0] state_next=$signed(state)+$signed(state_delta);
    wire signed [46:0] shelf_round=$signed(shelf_product)+47'sd2048;
    wire signed [34:0] y=$signed(input_d)+$signed(shelf_round >>> 12);
    always @(posedge clk) begin
        if (!rst_n || reset || !input_valid) begin
            state<=0; phase<=0; valid_d<=0; state_product<=0; shelf_product<=0;
            input_d<=0; output_q8<=0; output_valid<=0; saturated<=0;
        end else begin
            phase<=~phase;
            shelf_product<=difference*gain_delta; input_d<=input_q8; valid_d<=1;
            output_q8<=y>33554431 ? 26'sh1ffffff : y < -33554432 ? 26'sh2000000 : y[25:0];
            output_valid<=valid_d;
            saturated<=y>33554431 || y < -33554432;
            if (!phase) state_product<=difference*$signed({1'b0,alpha_safe});
            else state<=state_next>55'sd562949953421311 ? 50'sh1ffffffffffff :
                       state_next < -55'sd562949953421312 ? 50'sh2000000000000 : state_next[49:0];
        end
    end
endmodule
