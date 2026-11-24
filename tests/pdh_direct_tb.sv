`timescale 1ns / 1ps
module pdh_direct_tb;
    reg clk=0, gpio_clk=0, rst_n=0;
    always #2.034505 clk=~clk;
    always #5.137 gpio_clk=~gpio_clk;
    reg [31:0] control=0, amplitudes=0, reference_settings=0;
    reg [47:0] c=48'd98170681051429, m=48'd4908534052571;
    wire [31:0] status, version;
    wire [223:0] sum_data;
    wire [127:0] ref_data;
    reg ready=1;
    pdh_tones dut (.clk(clk),.gpio_clk(gpio_clk),.rst_n(rst_n),.control(control),
        .amplitudes(amplitudes),.reference_settings(reference_settings),
        .carrier_fcw_low(c[31:0]),.carrier_fcw_high({16'd0,c[47:32]}),
        .modulation_fcw_low(m[31:0]),.modulation_fcw_high({16'd0,m[47:32]}),
        .status(status),.feature_version(version),.m_sum_tdata(sum_data),
        .m_sum_tvalid(),.m_sum_tready(ready),.m_ref_tdata(ref_data),.m_ref_tvalid(),.m_ref_tready(ready));
    integer out, tick=0, profile=0;
    reg log_samples=0;
    reg [47:0] last_c, last_m, last_cp, last_mp, last_cs, last_ms;
    always @(posedge clk) begin
        last_c=dut.carrier_active; last_m=dut.modulation_active;
        last_cp=dut.carrier.frame_phase; last_mp=dut.modulation.frame_phase;
        last_cs=dut.carrier.frame_step; last_ms=dut.modulation.frame_step;
        #0.001;
        if (rst_n) begin
            if (dut.carrier.frame_phase !== ((last_cp+last_cs)&48'hffffffffffff)) $fatal(1,"Carrier phase discontinuity");
            if (dut.modulation.frame_phase !== ((last_mp+last_ms)&48'hffffffffffff)) $fatal(1,"Modulation phase discontinuity");
            if ((dut.carrier_active>last_c ? dut.carrier_active-last_c : last_c-dut.carrier_active)>1024) $fatal(1,"Carrier slew too fast");
            if ((dut.modulation_active>last_m ? dut.modulation_active-last_m : last_m-dut.modulation_active)>1024) $fatal(1,"Modulation slew too fast");
        end
    end
    // Log phases presented to the lookup before the edge, and outputs after.
    always @(negedge clk) if (log_samples) begin
        $fdisplay(out,"%d %d %h %h %h %h %h %h %h %h",tick,profile,dut.carrier_phase,
            dut.modulation_phase,dut.reference_phase,dut.reference_phase_offset,sum_data,ref_data,dut.carrier_active,dut.modulation_active);
        tick=tick+1;
    end
    task commit;
        begin
            @(negedge gpio_clk); control=control^4;
            wait(status[2]==control[2]);
            repeat(20) @(negedge clk);
            if (status[6:3]!=0) $fatal(1,"Unexpected fault");
        end
    endtask
    initial begin
        out=$fopen("pdh_direct_samples.txt","w");
        repeat(10) @(negedge clk); rst_n=1;
        amplitudes={16'd7000,16'd18000}; reference_settings={16'd27307,16'd12000}; control=3;
        commit(); log_samples=1;
        repeat(600) @(negedge clk);
        // Change half a word WITHOUT commit: oscillator target must not change.
        c=c+48'd15003; m=m-48'd7051;
        repeat(100) @(negedge clk);
        if (dut.carrier_target!=48'd98170681051429) $fatal(1,"Uncommitted FCW applied");
        commit();
        repeat(600) @(negedge clk);
        if (dut.carrier_active!=c || dut.modulation_active!=m) $fatal(1,"Slew did not land exactly");
        // Reverse ramps; keep phase continuous and exact final FCW.
        c=c-48'd23003; m=m+48'd17215; commit();
        repeat(600) @(negedge clk);
        if (status[9:8]!=0) $fatal(1,"Ramps did not finish");
        log_samples=0; reference_settings={16'd60075,16'd12000}; commit();
        profile=1; log_samples=1; repeat(600) @(negedge clk); log_samples=0;
        // Frequency and reference phase remain live even while muted.
        control=control&~3; commit(); repeat(20) @(negedge clk);
        if (sum_data!=0 || ref_data!=0) $fatal(1,"Mute failed");
        control=control|3; commit(); ready=0; repeat(4) @(negedge clk); ready=1;
        repeat(5) @(negedge clk);
        if (!status[4] || !status[5] || sum_data!=0 || ref_data!=0) $fatal(1,"Stall not muted");
        $fclose(out); $display("PASS: PDH direct LUT, FCW commit/slew/continuity, mute/stall"); $finish;
    end
    initial begin #1000000; $fatal(1,"Timeout"); end
endmodule
