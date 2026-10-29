`timescale 1ns/1ps
// Sweep real branch crossings past each DAC rail, then unwind. Counter keeps
// every turn; only the output representation saturates. Three hardware ranges.
module laser_pll_wide_phase_tb;
    reg clk=0, rst_n=0, arm=0, invert=0;
    always #2 clk=~clk;
    reg signed [17:0] phase=0;
    reg signed [42:0] tracking_phase=43'sd26214400000;
    reg tracking_arm=0;
    reg [31:0] tracking_control=0;
    wire signed [15:0] dac[0:2], tracking_dac[0:2];
    wire signed [42:0] full_phase[0:2];
    wire valid[0:2], sat[0:2], tracking_valid[0:2], tracking_sat[0:2];
    wire [31:0] tracking_status[0:2];
    for (genvar s=0;s<3;s=s+1) begin: range_case
        wire signed [25:0] scaled_phase;
        laser_pll_unwrap #(.STAGE3_RANGE_SHIFT(s)) unwrap (
            .clk(clk),.rst_n(rst_n),.arm(arm),.phase_valid(1'b1),
            .phase_error(phase),.turns(),.unwrapped_error(full_phase[s]),
            .phase_for_dac(scaled_phase));
        laser_pll_phase_scale scale (
            .clk(clk),.rst_n(rst_n),.phase_codes(scaled_phase),.phase_valid(arm),
            .gain_shift(4'd0),.invert(invert),.dac_target(dac[s]),
            .target_valid(valid[s]),.saturated(sat[s]));
        laser_pll_tracking #(.STAGE3_RANGE_SHIFT(s)) tracking (
            .clk(clk),.rst_n(rst_n),.arm(tracking_arm),.phase_codes(tracking_phase),
            .phase_valid(1'b1),.held_dac(16'sd1234),.initial_gain_shift(4'd0),
            .invert(1'b0),.tracking_control(tracking_control),
            .dac_target(tracking_dac[s]),.target_valid(tracking_valid[s]),
            .saturated(tracking_sat[s]),.tracking_status(tracking_status[s]));
    end
    task tick; begin @(posedge clk); #0.1; end endtask
    integer expected, n, direction;
    longint signed expected_phase, raw_code;
    reg [25:0] old_gain[0:2];
    task check_phase(input integer quarter_turns);
        begin
            expected_phase=quarter_turns*64'sd65536;
            @(negedge clk); phase=expected_phase[17:0];
            repeat(6) tick;
            for (integer s=0;s<3;s=s+1) begin
                if (full_phase[s]!==expected_phase)
                    $fatal(1,"Lost wraps shift=%d qturn=%d got=%d",s,quarter_turns,full_phase[s]);
                raw_code=((expected_phase >>> s)*104858+33554432) >>> 26;
                expected=raw_code>32767 ? 32767 : raw_code < -32768 ? -32768 : raw_code;
                if (!valid[s] || dac[s]!==expected)
                    $fatal(1,"Wide scale shift=%d qturn=%d got=%d expected=%d",s,quarter_turns,dac[s],expected);
            end
        end
    endtask
    initial begin
        repeat(4) tick;
        @(negedge clk); rst_n=1; arm=1;
        check_phase(0);
        for(n=1;n<=4096;n=n+1) check_phase(n);
        for(n=4095;n>=-4096;n=n-1) check_phase(n);
        for(n=-4095;n<=0;n=n+1) check_phase(n);
        // +/-300 turns remains linear for the +/-320-turn build, including
        // a nonzero held bias. No forgotten phase while outside the DAC range.
        @(negedge clk); tracking_arm=1;
        repeat(12) tick;
        for(integer s=0;s<3;s=s+1)
            if(!tracking_valid[s] || tracking_dac[s]!=1234) $fatal(1,"Tracking entry bias");
        for(direction=-1;direction<=1;direction=direction+2) begin
            @(negedge clk); tracking_phase=43'sd26214400000+direction*43'sd78643200;
            repeat(8) tick;
            raw_code=(direction*64'sd78643200*104858+134217728) >>> 28;
            if(tracking_dac[2]!==1234+raw_code || tracking_sat[2])
                $fatal(1,"300 turns should remain linear at 640-turn span");
        end
        @(negedge clk); tracking_phase=43'sd26214400000;
        repeat(8) tick;
        // Stationary lock retains its DAC bias through all gain doublings.
        for(integer gain=0;gain<=8;gain=gain+1) begin
            @(negedge clk); tracking_control=gain;
            repeat(220) begin
                for(integer s=0;s<3;s=s+1) old_gain[s]=tracking_status[s][25:0];
                tick;
                for(integer s=0;s<3;s=s+1) begin
                    if(tracking_dac[s]!=1234 || tracking_sat[s]) $fatal(1,"Gain changed lock bias");
                    if(tracking_status[s][25:0]-old_gain[s]>(old_gain[s]>>8)) $fatal(1,"Gain jump");
                end
            end
            for(integer s=0;s<3;s=s+1)
                if(tracking_status[s][30] || tracking_status[s][25:0]!=(26'd104858<<gain))
                    $fatal(1,"Gain ramp did not settle");
        end
        @(negedge clk); tracking_phase=43'sd26214401000;
        repeat(6) tick;
        for(integer s=0;s<3;s=s+1)
            if(tracking_dac[s] != 1234+(400>>s)) $fatal(1,"Final sensitivity shift=%d",s);
        $display("PASS: 160/320/640-turn ranges; +/-1024-turn rail/unwind; +/-300-turn linearity; all smooth gains; unchanged pipeline");
        $finish;
    end
endmodule
