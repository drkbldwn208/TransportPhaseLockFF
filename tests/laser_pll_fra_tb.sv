`timescale 1ns / 1ps
module laser_pll_fra_tb;
    reg clk=0; always #2.0345 clk=~clk;
    reg rst_n=0;
    reg [31:0] control=0, settle=1024, measure=16384;
    wire [31:0] status;
    wire signed [15:0] driven;
    wire saturated;
    reg signed [15:0] feedback[0:3];
    reg clamp_test=0, internal_saturation=0, loop_test=0, rx_valid=1;
    reg signed [15:0] delayed_drive[0:3];
    wire signed [15:0] rx_i=2000+($signed(delayed_drive[3])-8192)/2;
    wire signed [15:0] rx_q=-1000+($signed(delayed_drive[3])-8192)/4;
    wire signed [23:0] rx_filtered_i=$signed(rx_i)*256;
    wire signed [23:0] rx_filtered_q=$signed(rx_q)*256;
    wire signed [63:0] sum_i,sum_q;
    always @(posedge clk) begin
        delayed_drive[0]<=driven;
        for(integer j=1;j<4;j=j+1) delayed_drive[j]<=delayed_drive[j-1];
    end
    wire [31:0] clip_samples,saturated_samples,outside_clip_samples,measured_samples,error_extrema,drive_extrema;
    wire signed [15:0] error_code=loop_test ? 16'sd8192 : clamp_test ? 16'sd32760 : feedback[3];
    wire [159:0] tone, error_probe, drive_probe;
    wire [271:0] reference, error_ref, drive_ref;
    wire tone_valid,tone_ready,ref_valid,ref_ready;
    wire error_valid,error_ready,drive_valid,drive_ready,error_ref_valid,error_ref_ready,drive_ref_valid,drive_ref_ready;
    integer measured=0;
    always @(posedge clk) begin
        if (!rst_n) for(integer j=0;j<4;j=j+1) feedback[j]<=0;
        else begin
            feedback[0]<=2000-$signed(driven)/2;
            for(integer j=1;j<4;j=j+1) feedback[j]<=feedback[j-1];
        end
        if (error_ref_valid && error_ref_ready && error_ref[256]) measured<=measured+1;
    end
    laser_pll_fra #(.RAMP_INTERVAL_LOG2(0)) dut(
        .clk(clk),.rst_n(rst_n),.error_code(error_code),.error_valid(1'b1),.error_saturated(internal_saturation),
        .loopback_i(rx_filtered_i), .loopback_q(rx_filtered_q), .loopback_valid(rx_valid), .loopback_clipped(1'b0), .loopback_sum_i(sum_i), .loopback_sum_q(sum_q),
        .dac_ready(1'b1),.phase_valid(!loop_test),.control(control),.settle_clocks(settle),.measure_clocks(measure),
        .clip_samples(clip_samples),.saturated_samples(saturated_samples),.outside_clip_samples(outside_clip_samples),
        .measured_samples(measured_samples),.error_extrema(error_extrema),.drive_extrema(drive_extrema),
        .status(status),.drive_code(driven),.drive_saturated(saturated),
        .s_tone_tdata(tone),.s_tone_tvalid(tone_valid),.s_tone_tready(tone_ready),
        .s_ref_tdata(reference),.s_ref_tvalid(ref_valid),.s_ref_tready(ref_ready),
        .m_error_tdata(error_probe),.m_error_tvalid(error_valid),.m_error_tready(error_ready),
        .m_drive_tdata(drive_probe),.m_drive_tvalid(drive_valid),.m_drive_tready(drive_ready),
        .m_error_ref_tdata(error_ref),.m_error_ref_tvalid(error_ref_valid),.m_error_ref_tready(error_ref_ready),
        .m_drive_ref_tdata(drive_ref),.m_drive_ref_tvalid(drive_ref_valid),.m_drive_ref_tready(drive_ref_ready));
    reg [6:0] awaddr[0:2],araddr[0:2];
    reg [31:0] wdata[0:2];
    reg [2:0] awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    wire [2:0] awready,wready,bvalid,arready,rvalid;
    wire [31:0] rdata[0:2];
    perturbation_gen generator(.ap_clk(clk),.ap_rst_n(rst_n),
        .s_axi_ctrl_AWADDR(awaddr[0]),
        .s_axi_ctrl_AWVALID(awvalid[0]),
        .s_axi_ctrl_AWREADY(awready[0]),
        .s_axi_ctrl_WDATA(wdata[0]),
        .s_axi_ctrl_WVALID(wvalid[0]),
        .s_axi_ctrl_WREADY(wready[0]),
        .s_axi_ctrl_BVALID(bvalid[0]),
        .s_axi_ctrl_BREADY(bready[0]),
        .s_axi_ctrl_ARADDR(araddr[0]),
        .s_axi_ctrl_ARVALID(arvalid[0]),
        .s_axi_ctrl_ARREADY(arready[0]),
        .s_axi_ctrl_RDATA(rdata[0]),
        .s_axi_ctrl_RVALID(rvalid[0]),
        .s_axi_ctrl_RREADY(rready[0]),
        .s_axi_ctrl_WSTRB(4'hf),
        .perturb_err_out_TDATA(tone),.perturb_err_out_TVALID(tone_valid),.perturb_err_out_TREADY(tone_ready),
        .ref_out_TDATA(reference),.ref_out_TVALID(ref_valid),.ref_out_TREADY(ref_ready),
        .perturb_nco_out_TREADY(1'b1));
    demod_err return_demod(.ap_clk(clk),.ap_rst_n(rst_n),
        .s_axi_ctrl_AWADDR(awaddr[1]),
        .s_axi_ctrl_AWVALID(awvalid[1]),
        .s_axi_ctrl_AWREADY(awready[1]),
        .s_axi_ctrl_WDATA(wdata[1]),
        .s_axi_ctrl_WVALID(wvalid[1]),
        .s_axi_ctrl_WREADY(wready[1]),
        .s_axi_ctrl_BVALID(bvalid[1]),
        .s_axi_ctrl_BREADY(bready[1]),
        .s_axi_ctrl_ARADDR(araddr[1]),
        .s_axi_ctrl_ARVALID(arvalid[1]),
        .s_axi_ctrl_ARREADY(arready[1]),
        .s_axi_ctrl_RDATA(rdata[1]),
        .s_axi_ctrl_RVALID(rvalid[1]),
        .s_axi_ctrl_RREADY(rready[1]),
        .s_axi_ctrl_WSTRB(4'hf),
        .probe_in_TDATA(error_probe),.probe_in_TVALID(error_valid),.probe_in_TREADY(error_ready),
        .ref_in_TDATA(error_ref),.ref_in_TVALID(error_ref_valid),.ref_in_TREADY(error_ref_ready));
    demod_err drive_demod(.ap_clk(clk),.ap_rst_n(rst_n),
        .s_axi_ctrl_AWADDR(awaddr[2]),
        .s_axi_ctrl_AWVALID(awvalid[2]),
        .s_axi_ctrl_AWREADY(awready[2]),
        .s_axi_ctrl_WDATA(wdata[2]),
        .s_axi_ctrl_WVALID(wvalid[2]),
        .s_axi_ctrl_WREADY(wready[2]),
        .s_axi_ctrl_BVALID(bvalid[2]),
        .s_axi_ctrl_BREADY(bready[2]),
        .s_axi_ctrl_ARADDR(araddr[2]),
        .s_axi_ctrl_ARVALID(arvalid[2]),
        .s_axi_ctrl_ARREADY(arready[2]),
        .s_axi_ctrl_RDATA(rdata[2]),
        .s_axi_ctrl_RVALID(rvalid[2]),
        .s_axi_ctrl_RREADY(rready[2]),
        .s_axi_ctrl_WSTRB(4'hf),
        .probe_in_TDATA(drive_probe),.probe_in_TVALID(drive_valid),.probe_in_TREADY(drive_ready),
        .ref_in_TDATA(drive_ref),.ref_in_TVALID(drive_ref_valid),.ref_in_TREADY(drive_ref_ready));
    task write_reg(input integer ip,input [6:0] address,input [31:0] value);
        begin
            @(negedge clk); awaddr[ip]=address; awvalid[ip]=1;
            do @(posedge clk); while(!awready[ip]);
            @(negedge clk); awvalid[ip]=0; wdata[ip]=value; wvalid[ip]=1;
            do @(posedge clk); while(!wready[ip]);
            @(negedge clk); wvalid[ip]=0; bready[ip]=1;
            do @(posedge clk); while(!bvalid[ip]);
            @(negedge clk); bready[ip]=0;
        end
    endtask
    task read_reg(input integer ip,input [6:0] address,output [31:0] value);
        begin
            @(negedge clk); araddr[ip]=address; arvalid[ip]=1;
            do @(posedge clk); while(!arready[ip]);
            @(negedge clk); arvalid[ip]=0; rready[ip]=1;
            do @(posedge clk); while(!rvalid[ip]);
            value=rdata[ip];
            @(negedge clk); rready[ip]=0;
        end
    endtask
    task read_sum(input integer ip,input [6:0] address,output reg signed [71:0] value);
        reg [31:0] v;
        begin
            read_reg(ip,address,v); value[31:0]=v;
            read_reg(ip,address+4,v); value[63:32]=v;
            read_reg(ip,address+8,v); value[71:64]=v[7:0];
        end
    endtask
    task wait_done;
        integer timeout_cycles;
        begin
            timeout_cycles=0;
            while(!status[2]) begin
                @(negedge clk); timeout_cycles=timeout_cycles+1;
                if(timeout_cycles>200000) $fatal(1,"FRA completion timeout");
            end
            repeat(32) @(negedge clk);
            if(driven!==error_code) $fatal(1,"stimulus remains after completion");
        end
    endtask
    reg signed [71:0] ei,eq,ui,uq;
    reg [31:0] value;
    integer f, before_count, word;
    initial begin
        f=$fopen("fra_sums.txt","w");
        repeat(12) @(negedge clk); rst_n=1;
        repeat(20) @(negedge clk);
        write_reg(0,'h18,1024); write_reg(0,'h20,0);
        write_reg(0,'h28,32'hffffffff); write_reg(0,'h2c,255);
        write_reg(0,'h34,1); write_reg(0,'h38,0);
        for(integer k=0;k<2;k=k+1) begin
            word=k==0 ? 2097152 : 131072; // 960 kHz / 60 kHz, exact whole cycles.
            write_reg(0,'h18,k==0 ? 1024 : 20'hffc00); // reverse probe polarity
            write_reg(0,'h10,word); write_reg(0,'h40,0); write_reg(0,'h40,1);
            repeat(128) @(negedge clk);
            before_count=measured; control=1;
            wait_done();
            if(status[7:3]!=0) $fatal(1,"unexpected faults %h",status);
            if(measured_samples!=measure || clip_samples!=0 || saturated_samples!=0) $fatal(1,"diagnostic counts wrong");
            if(measured-before_count!=measure) $fatal(1,"measurement sample count %d",measured-before_count);
            read_reg(1,'h10,value); if(value!=1) $fatal(1,"return demod incomplete");
            read_reg(2,'h10,value); if(value!=1) $fatal(1,"drive demod incomplete");
            read_sum(1,'h20,ei); read_sum(1,'h40,eq);
            read_sum(2,'h20,ui); read_sum(2,'h40,uq);
            $fdisplay(f,"%d %d %d %d %d",word,ei,eq,ui,uq);
            control=0; repeat(32) @(negedge clk);
        end
        // Clipping during settling does not veto a clean measurement window.
        internal_saturation=1; control=1;
        wait(dut.state==2); repeat(64) @(negedge clk); internal_saturation=0;
        wait_done();
        if(status[3] || clip_samples || saturated_samples || outside_clip_samples==0)
            $fatal(1,"settling clipping contaminated integration flag");
        control=0; repeat(32) @(negedge clk);
        // Bounded final output with an internal limiter is identified separately.
        control=1; wait(status[1]); @(negedge clk); internal_saturation=1;
        repeat(7) @(negedge clk); internal_saturation=0;
        wait_done();
        if(!status[3] || clip_samples!=0 || saturated_samples!=7)
            $fatal(1,"internal clipping not separated from DAC clipping");
        control=0; repeat(32) @(negedge clk);
        // Operator abort ramps down and flags an incomplete acquisition.
        control=1; repeat(1000) @(negedge clk); control=0; wait_done();
        if(!status[7]) $fatal(1,"abort not recorded");
        repeat(4) @(negedge clk);
        // The physical DAC sum must saturate instead of wrapping.
        clamp_test=1; control=1; wait_done();
        if(!status[3] || clip_samples==0 || saturated_samples!=0) $fatal(1,"DAC clipping not recorded");
        control=0; clamp_test=0; repeat(32) @(negedge clk);
        $fclose(f);
        f=$fopen("loopback_sums.txt","w");
        loop_test=1;
        for(integer k=0;k<2;k=k+1) begin
            word=k==0 ? 2097152 : 131072;
            write_reg(0,'h18,1024); write_reg(0,'h10,word);
            write_reg(0,'h40,0); write_reg(0,'h40,1);
            repeat(128) @(negedge clk); control=3; wait_done();
            if(status[7:3]!=0) $fatal(1,"loopback must not require phase-detector validity: %h",status);
            if(measured_samples!=measure) $fatal(1,"loopback window count");
            read_sum(1,'h20,ei); read_sum(1,'h40,eq);
            read_sum(2,'h20,ui); read_sum(2,'h40,uq);
            $fdisplay(f,"%d %d %d %d %d %d %d",word,ei,eq,ui,uq,sum_i,sum_q);
            control=0; repeat(32) @(negedge clk);
        end
        control=3; wait(status[1]); @(negedge clk); rx_valid=0;
        repeat(7) @(negedge clk); rx_valid=1; wait_done();
        if(!status[4]) $fatal(1,"missing IQ samples not flagged");
        control=0; repeat(32) @(negedge clk);
        $fclose(f);
        loop_test=0;
        // Backpressure cannot alter feedback or silently yield a shorter window.
        control=1; wait(status[1]);
        force error_ready=0; repeat(32) @(negedge clk); release error_ready;
        wait_done(); if(!status[5]) $fatal(1,"probe loss not recorded");
        control=0; repeat(32) @(negedge clk);
        $display("PASS: original HLS generator/demods, simultaneous E/U, exact windows, idle identity, abort ramp, clipping and loss flags");
        $finish;
    end
    initial begin #5000000; $fatal(1,"global timeout"); end
endmodule
