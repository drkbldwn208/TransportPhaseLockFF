`timescale 1ns/1ps
// Compare RTL against exact /640 arithmetic, independent of its reciprocal.
module laser_pll_phase_scale_tb;
    reg clk=0;
    always #2 clk=~clk;
    reg rst_n=0, valid=0, invert=0;
    reg [3:0] gain=0;
    reg signed [25:0] phase=0;
    wire signed [15:0] dac;
    wire out_valid, saturated;
    laser_pll_phase_scale scale(.clk(clk),.rst_n(rst_n),.phase_codes(phase),
        .phase_valid(valid),.gain_shift(gain),.invert(invert),
        .dac_target(dac),.target_valid(out_valid),.saturated(saturated));
    reg error_valid=0, arm=0;
    reg signed [17:0] measured=0;
    wire signed [15:0] error_dac;
    wire error_out_valid, error_sat;
    wire signed [23:0] turns;
    laser_pll_error error_detector(.clk(clk),.rst_n(rst_n),.measured_phase(measured),
        .phase_valid(error_valid),.control(32'd1),.phase_offset(32'd0),.unwrap_arm(arm),
        .phase_error(),.frequency_error(),.error_valid(),.dac_target(),.target_valid(),
        .target_saturated(),.unwrapped_target(error_dac),.unwrapped_saturated(error_sat),
        .unwrapped_valid(error_out_valid),.capture_target(),.capture_saturated(),.turns(turns));
    integer expected[0:2], phase_expected[0:3];
    reg expected_valid[0:2], phase_expected_valid[0:3];
    integer cases=0;
    function integer ideal(input integer p, input integer g, input integer inv);
        real value;
        begin
            value=p*(2.0**g)/640.0;
            if (inv) value=-value;
            ideal=value>=32767 ? 32767 : value<=-32768 ? -32768 : $rtoi($floor(value+0.5));
        end
    endfunction
    task sample(input integer p, input integer g, input integer inv, input integer v);
        begin
            @(negedge clk); phase=p; gain=g; invert=inv; valid=v;
            for (integer j=2;j>0;j=j-1) begin
                expected[j]=expected[j-1]; expected_valid[j]=expected_valid[j-1];
            end
            expected[0]=ideal(p,g,inv); expected_valid[0]=v;
            @(posedge clk); #0.1;
            if (out_valid!==expected_valid[2]) $fatal(1,"Scaler latency/valid alignment");
            if (out_valid && ($signed(dac)-expected[2]>1 || $signed(dac)-expected[2] < -1))
                $fatal(1,"Scaled phase mismatch got=%d ideal=%d",dac,expected[2]);
            if (!out_valid && (dac!=0 || saturated)) $fatal(1,"Invalid scaler output not zero");
            if (out_valid && expected[2]>-32766 && expected[2]<32766 && saturated)
                $fatal(1,"Linear phase falsely reported as saturated");
            cases=cases+1;
        end
    endtask
    task phase_sample(input integer true_phase, input integer v);
        begin
            @(negedge clk); measured=-true_phase; error_valid=v; arm=1;
            for (integer j=3;j>0;j=j-1) begin
                phase_expected[j]=phase_expected[j-1]; phase_expected_valid[j]=phase_expected_valid[j-1];
            end
            phase_expected[0]=ideal(true_phase,0,0); phase_expected_valid[0]=v;
            @(posedge clk); #0.1;
            if (error_out_valid!==phase_expected_valid[3]) $fatal(1,"Error/scaler latency mismatch");
            if (error_out_valid && ($signed(error_dac)-phase_expected[3]>1 ||
                                   $signed(error_dac)-phase_expected[3] < -1))
                $fatal(1,"Unwrapped ramp mismatch got=%d ideal=%d turns=%d",error_dac,phase_expected[3],turns);
        end
    endtask
    initial begin
        for (integer j=0;j<3;j=j+1) begin expected[j]=0; expected_valid[j]=0; end
        for (integer j=0;j<4;j=j+1) begin phase_expected[j]=0; phase_expected_valid[j]=0; end
        repeat(4) @(posedge clk);
        @(negedge clk); rst_n=1;
        // Every gain/polarity, numeric endpoints, near-zero and rail boundaries.
        for (integer g=0;g<16;g=g+1) begin
            for (integer inv=0;inv<2;inv=inv+1) begin
                sample(-33554432,g,inv,1); sample(33554431,g,inv,1);
                for (integer p=-640;p<=640;p=p+32) sample(p,g,inv,1);
                for (integer delta=-1024;delta<=1024;delta=delta+16) begin
                    sample((20971520>>g)+delta,g,inv,1);
                    sample(-(20971520>>g)+delta,g,inv,1);
                end
            end
        end
        // Changing controls/valid each clock checks metadata alignment.
        for (integer n=0;n<2000;n=n+1)
            sample($signed($urandom_range(0,67108863))-33554432,n%16,n%2,n%7!=0);
        repeat(4) sample(0,0,0,0);
        // Accumulate ~381 turns, remain railed, then unwind to the origin.
        // Cross +/-128-turn datapath bounds without clearing the 24-bit memory.
        for (integer direction=-1;direction<=1;direction=direction+2) begin
            repeat(6) phase_sample(0,0);
            for (integer k=0;k<=10000;k=k+1) phase_sample(direction*k*10000,1);
            repeat(20) phase_sample(direction*100000000,1);
            if (!error_sat || (direction>0 ? turns<300 : turns>-300))
                $fatal(1,"Rail discarded remembered turns");
            for (integer k=10000;k>=0;k=k-1) phase_sample(direction*k*10000,1);
            repeat(6) phase_sample(0,1);
            if (error_dac!=0 || error_sat || turns!=0) $fatal(1,"Unwinding did not return to zero");
        end
        repeat(6) phase_sample(0,0);
        if (turns!=0 || error_out_valid) $fatal(1,"Gap/disarm did not reset history");
        $display("PASS: %d scaler vectors, all gains/polarities; 3-register latency; >300 turns in both directions, saturation and complete unwinding",cases);
        $finish;
    end
endmodule
