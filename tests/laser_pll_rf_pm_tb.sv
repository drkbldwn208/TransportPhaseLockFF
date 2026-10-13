`timescale 1ns/1ps
module laser_pll_rf_pm_tb;
    reg clk=0;always #2 clk=~clk;
    reg rst_n=0,ready=1;
    reg signed [19:0] phase=0;
    reg [15:0] amplitude=0;
    wire [223:0] data;
    wire valid;
    wire signed [17:0] applied;
    laser_pll_rf_pm dut(.clk(clk),.rst_n(rst_n),.phase_command(phase),.amplitude(amplitude),
        .m_axis_tdata(data),.m_axis_tvalid(valid),.m_axis_tready(ready),.applied_phase(applied));
    integer i,q,expected_amp,k,a;
    real angle,error_i,error_q,radius;
    reg [223:0] held;
    reg signed [17:0] held_phase;
    task check(input integer p,input integer amp);
        begin
            @(negedge clk);phase=p;amplitude=amp;
            repeat(5) @(posedge clk);
            #1;i=$signed(data[15:0]);q=$signed(data[31:16]);expected_amp=amp>32767?32767:amp;
            angle=$itor($signed(applied))*6.283185307179586/262144.0;
            error_i=i-expected_amp*$cos(angle);error_q=q-expected_amp*$sin(angle);
            radius=$sqrt(i*1.0*i+q*1.0*q);
            if(!valid || error_i>1.1 || error_i< -1.1 || error_q>1.1 || error_q< -1.1)
                $fatal(1,"I/Q/phase mismatch p=%d A=%d I=%d Q=%d errors=%f,%f",p,amp,i,q,error_i,error_q);
            if(radius>expected_amp+1.1 || radius<expected_amp-1.1)$fatal(1,"Envelope mismatch");
            for(integer lane=1;lane<7;lane=lane+1)
                if(data[32*lane+:32]!==data[31:0])$fatal(1,"Packing mismatch");
            if(p==0 && (i!=expected_amp || q!=0 || applied!=0))$fatal(1,"Idle constant changed");
        end
    endtask
    initial begin
        repeat(5)@(posedge clk);@(negedge clk);rst_n=1;
        for(a=0;a<4;a=a+1)begin
            case(a)0:amplitude=0;1:amplitude=8192;2:amplitude=32767;3:amplitude=65535;endcase
            for(k=-131072;k<131072;k=k+9973)check(k,amplitude);
            check(0,amplitude);check(209,amplitude);check(-209,amplitude);
            check(8344,amplitude);check(-8344,amplitude);
        end
        held=data;held_phase=applied;@(negedge clk);ready=0;phase=40960;
        repeat(8)begin @(posedge clk);#1;if(data!==held || applied!==held_phase)$fatal(1,"Output changed during stall");end
        @(negedge clk);ready=1;check(40960,8192);
        $display("PASS: RF PM quadrants, 0/full/clamped amplitude, constant envelope, idle identity, packing and stalls");
        $finish;
    end
endmodule
