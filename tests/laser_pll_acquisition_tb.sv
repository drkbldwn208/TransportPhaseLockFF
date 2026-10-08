`timescale 1ns/1ps
module laser_pll_acquisition_tb;
    reg clk=0;
    always #2 clk=~clk;
    task tick; begin @(posedge clk); #0.1; end endtask
    reg rst_n=0, ready=1;
    reg [31:0] cfg=32'h00200000, dc=0, control=5;
    reg [9:0] bin=104;
    reg fft_valid=1, valid=1;
    reg signed [15:0] legacy=800, capture=-200, unwrapped=300;
    wire signed [15:0] output_code;
    wire output_valid, saturated, arm;
    wire [31:0] status;
    laser_pll_acquisition dut(.clk(clk),.rst_n(rst_n),.ready(ready),
        .acquisition_control(cfg),.test_dc(dc),.control(control),
        .reference_frequency(48'd114532461226667), // exactly 800 MHz to FCW rounding
        .fft_bin(bin),.fft_valid(fft_valid),.error_valid(valid),
        .legacy_target(legacy),.legacy_saturated(1'b0),.capture_target(capture),.capture_saturated(1'b0),
        .unwrapped_target(unwrapped),.unwrapped_saturated(1'b0),.target_valid(valid),.turns(24'sd0),
        .unwrap_arm(arm),.dac_target(output_code),.output_valid(output_valid),
        .output_saturated(saturated),.acquisition_status(status));
    reg slip_arm=0, slip_valid=0;
    reg signed [17:0] wrapped=0;
    wire signed [23:0] turns;
    wire signed [42:0] continuous_phase;
    laser_pll_unwrap memory(.clk(clk),.rst_n(rst_n),.arm(slip_arm),.phase_valid(slip_valid),
        .phase_error(wrapped),.turns(turns),.unwrapped_error(continuous_phase),.phase_for_dac());
    integer before_code, old_mode, true_phase, expected_turns;
    task request_stage(input integer mode);
        integer cycles;
        begin
            @(negedge clk); before_code=output_code; cfg=(cfg & ~7)|mode;
            tick;
            if (mode==3) begin
                cycles=0;
                while (status[2:0]!=3 && cycles<8) begin before_code=output_code; tick; cycles=cycles+1; end
            end
            if (status[2:0]!==mode[2:0]) $fatal(1,"Qualified stage was not accepted %d %h",mode,status);
            if (output_code!==before_code) $fatal(1,"Mode switch stepped from %d to %d",before_code,output_code);
        end
    endtask
    task settle;
        integer steps, previous, difference;
        begin
            steps=0; previous=output_code;
            while (status[3]) begin
                tick; steps=steps+1; difference=output_code-previous;
                if (difference>1 || difference < -1) $fatal(1,"Handoff >1 DAC code/clock: %d",difference);
                previous=output_code;
                if (steps>65540) $fatal(1,"Handoff never settled");
            end
            tick;
        end
    endtask
    initial begin
        repeat(4) tick; @(negedge clk); rst_n=1;
        repeat(6) tick;
        if (output_code!=800) $fatal(1,"Legacy selection");
        request_stage(1); settle;
        if (output_code!=-32768) $fatal(1,"200 MHz wide-capture polarity %d",output_code);
        @(negedge clk); cfg=(cfg & ~7)|2;
        repeat(10) tick;
        if (status[2:0]!=1 || !status[4]) $fatal(1,"Aliased/out-of-band handoff accepted");
        // Cancel before moving the tone, then exercise an accepted near handoff.
        @(negedge clk); cfg=(cfg & ~7)|1; bin=417;
        repeat(10) tick;
        if (output_code<160 || output_code>180) $fatal(1,"FFT frequency units %d",output_code);
        request_stage(2); settle;
        if (output_code!=-200) $fatal(1,"Capture target");
        // Invalid fine data still blocks entry, even with an explicit request.
        @(negedge clk); valid=0; cfg=(cfg & ~7)|3;
        repeat(10) tick;
        if (status[2:0]!=2 || !status[4] || status[6] || arm) $fatal(1,"Invalid phase permitted entry");
        @(negedge clk); cfg=(cfg & ~7)|2;
        tick;
        // Entry has no dwell or FFT requirement, including a distant/stale bin.
        @(negedge clk); valid=1; fft_valid=0; bin=104;
        tick;
        if (!status[6]) $fatal(1,"Valid fine data not ready");
        request_stage(3); settle;
        if (output_code!=300 || !arm) $fatal(1,"Unwrapped target");
        // Once settled, fast changes pass through exactly one register.
        @(negedge clk); unwrapped=1300;
        tick; if (output_code!=1300) $fatal(1,"Unexpected steady-state smoothing");
        @(negedge clk); fft_valid=1; bin=417;
        repeat(4) tick;
        request_stage(2);
        repeat(100) tick;
        request_stage(3); // retrigger during a ramp, preserving current output
        settle;
        request_stage(2); settle;
        // An apparently far-away valid FFT also must not veto manual stage 3.
        @(negedge clk); bin=104;
        repeat(4) tick;
        request_stage(3); settle;
        // DC works without ADC/fine validity and bypasses inverted polarity.
        @(negedge clk); valid=0; fft_valid=0; dc=-1234;
        request_stage(4); settle;
        if (output_code!=-1234 || !output_valid) $fatal(1,"DC bypass depends on detector");
        @(negedge clk); ready=0; dc=1234;
        repeat(10) begin tick; if (output_code!=-1234) $fatal(1,"Stalled output changed"); end
        @(negedge clk); ready=1;
        tick; if (output_code!=1234) $fatal(1,"Literal DC update failed");
        @(negedge clk); dc=0;
        tick; if (output_code!=0) $fatal(1,"Zero DC test failed");
        @(negedge clk); rst_n=0;
        tick; if (output_code!=0 || output_valid) $fatal(1,"Reset did not mute");
        @(negedge clk); rst_n=1; slip_arm=1; slip_valid=1;
        // Check both slip signs against an independent true-phase ramp.
        for (integer direction=-1;direction<=1;direction=direction+2) begin
            @(negedge clk); slip_arm=0; wrapped=0;
            tick;
            @(negedge clk); slip_arm=1;
            for (integer k=0;k<30000;k=k+1) begin
                true_phase=direction*k*10000;
                @(negedge clk); wrapped=true_phase;
                tick;
                expected_turns=(true_phase-$signed(wrapped))/262144;
                if (turns!=expected_turns) $fatal(1,"Slip sign/count error %d %d",turns,expected_turns);
                if (continuous_phase!=($signed(wrapped)+262144*expected_turns)) $fatal(1,"Unwrapped sample mismatch");
            end
        end
        // Invalid data breaks cycle history; do not count across missing samples.
        @(negedge clk); slip_valid=0;
        tick; if (turns!=0) $fatal(1,"Gap left stale turns");
        @(negedge clk); slip_valid=1; wrapped=120000;
        tick; if (turns!=0) $fatal(1,"Gap created a fictitious slip");
        // Seed the numeric endpoints: exercise full width without simulating
        // millions of optical cycles. A positive count must not become negative.
        @(negedge clk); wrapped=130000;
        tick;
        @(negedge clk); memory.turns=24'sh7fffff; wrapped=-130000;
        tick;
        if (turns!=24'sh7fffff || continuous_phase<0) $fatal(1,"Positive counter overflow");
        @(negedge clk); memory.turns=24'sh800000; wrapped=130000;
        tick;
        if (turns!=24'sh800000 || continuous_phase>0) $fatal(1,"Negative counter overflow");
        @(negedge clk); memory.turns=24'sd32767; wrapped=-130000;
        tick;
        if (turns!=32768) $fatal(1,"Counter accidentally limited to 16 bits");
        $display("PASS: manual fine entry without dwell/FFT gates; invalid-data rejection; handoffs; one-cycle path; DC/stalls; 24-bit slips/gaps");
        $finish;
    end
endmodule
