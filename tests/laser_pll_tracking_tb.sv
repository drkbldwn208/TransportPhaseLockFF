`timescale 1ns/1ps
module laser_pll_tracking_tb;
    reg clk=0;
    always #2 clk=~clk;
    reg rst_n=0, arm=0, valid=1, invert=0;
    reg signed [42:0] phase=43'sd26214401234;
    reg [31:0] cfg=0;
    wire signed [15:0] dac;
    wire out_valid, saturated;
    wire [31:0] status;
    laser_pll_tracking dut(.clk(clk),.rst_n(rst_n),.arm(arm),.phase_codes(phase),
        .phase_valid(valid),.held_dac(16'sd1234),.initial_gain_shift(4'd0),
        .invert(invert),.tracking_control(cfg),.dac_target(dac),
        .target_valid(out_valid),.saturated(saturated),.tracking_status(status));
    task tick; begin @(posedge clk); #0.1; end endtask
    integer old_dac, delta;
    reg [25:0] old_gain;
    initial begin
        repeat(4) tick;
        @(negedge clk); rst_n=1; arm=1;
        repeat(12) tick;
        if (!out_valid || dac!=1234) $fatal(1,"Tracking did not preserve acquired DAC bias");
        // Stationary phase at a large absolute slip count: no DC kick at any gain.
        for (integer shift=0;shift<=8;shift=shift+1) begin
            @(negedge clk); cfg=shift;
            repeat(220) begin
                old_gain=status[25:0]; tick;
                if (dac!=1234 || saturated) $fatal(1,"Gain ramp moved stationary lock point");
                if (status[25:0]<old_gain || status[25:0]-old_gain>(old_gain>>8))
                    $fatal(1,"Gain did not increase smoothly");
            end
            if (status[30] || status[25:0]!=(26'd104858<<shift)) $fatal(1,"Gain target not reached");
        end
        // 1000 phase codes at 256x gain = 400 DAC codes, independent of origin.
        @(negedge clk); phase=43'sd26214402234;
        repeat(5) begin tick; if (dac!=1234) $fatal(1,"Tracking pipeline shorter than six registers"); end
        tick;
        if (dac!=1634) $fatal(1,"Tracking phase sensitivity wrong: %d",dac);
        @(negedge clk); cfg=0;
        repeat(1800) begin
            old_dac=dac; old_gain=status[25:0]; tick; delta=$signed(dac)-old_dac;
            if (delta>0 || delta < -3) $fatal(1,"Decreasing gain stepped DAC: %d",delta);
            if (status[25:0]>old_gain || old_gain-status[25:0]>(old_gain>>8))
                $fatal(1,"Gain did not decrease smoothly");
        end
        if (dac!=1236 || status[30]) $fatal(1,"Gain-down did not settle");
        // Retarget during a ramp; coefficient must never jump directly to target.
        @(negedge clk); cfg=8;
        repeat(100) tick;
        @(negedge clk); cfg=0;
        repeat(120) tick;
        if (status[30]) $fatal(1,"Mid-ramp reversal failed");
        // Large excursions rail with correct sign; returning restores the bias.
        @(negedge clk); phase=43'sd26214401234+43'sd1000000000;
        repeat(8) tick;
        if (dac!=32767 || !saturated) $fatal(1,"Positive slip rail");
        @(negedge clk); phase=43'sd26214401234-43'sd1000000000;
        repeat(8) tick;
        if (dac!=-32768 || !saturated) $fatal(1,"Negative slip rail");
        @(negedge clk); phase=43'sd26214401234;
        repeat(8) tick;
        if (dac!=1234 || saturated) $fatal(1,"Excursion changed origin or bias");
        // Sign and invalid-data behavior, then a new acquisition at negative turns.
        @(negedge clk); invert=1; phase=43'sd26214402234;
        repeat(8) tick;
        if (dac!=1232) $fatal(1,"Polarity");
        @(negedge clk); valid=0;
        tick; if (out_valid || status[31] || dac!=0) $fatal(1,"Gap did not mute/reset anchor");
        @(negedge clk); valid=1; phase=-43'sd12345678901;
        repeat(12) tick;
        if (!out_valid || dac!=1234) $fatal(1,"Fresh origin after gap");
        @(negedge clk); arm=0;
        tick; if (out_valid || dac!=0) $fatal(1,"Disarm");
        $display("PASS: tracking preserves phase/bias; all 9 shifts; bounded bidirectional ramps; retarget; large slips; polarity and gaps");
        $finish;
    end
endmodule
