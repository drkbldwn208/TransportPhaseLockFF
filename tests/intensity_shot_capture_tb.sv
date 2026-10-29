`timescale 1ns/1ps
module intensity_shot_capture_tb;
    reg clk=0; always #2 clk=~clk;
    reg rst_n=0, active=0, sample_valid=1, ready=1;
    reg [31:0] control=0, tail_clocks=0;
    reg [15:0] flags=0;
    reg [31:0] ticks=0;
    always @(posedge clk) ticks<=ticks+1;
    wire [127:0] data;
    wire valid,last,fifo_rst_n;
    wire [31:0] status,signature;
    intensity_shot_capture dut(.clk(clk),.rst_n(rst_n),.shot_active(active),
        .sample_valid(sample_valid),.error_q8(ticks<<8),.reference_power(16'd1000),
        .measured_power(16'd900),.actuator_codes(16'd6000),.raw_adc(-16'sd100),
        .sample_flags(flags),.control(control),.tail_clocks(tail_clocks),
        .status(status),.feature_version(signature),.fifo_rst_n(fifo_rst_n),
        .m_axis_tdata(data),.m_axis_tvalid(valid),.m_axis_tlast(last),.m_axis_tready(ready));
    integer received=0, last_seen=0;
    reg [15:0] flags_seen=0;
    reg [31:0] first_tick=0, previous_tick=0;
    reg check_spacing=1;
    reg stalled=0;
    reg [128:0] stalled_data;
    always @(posedge clk) begin
        if (stalled && {last,data}!==stalled_data) $fatal(1,"AXIS changed under backpressure");
        stalled<=valid && !ready;
        if (valid && !ready) stalled_data<={last,data};
        if (valid && ready) begin
            if (data[63:32]!=={16'd900,16'd1000} || data[95:64]!=={16'hff9c,16'd6000})
                $fatal(1,"Frame layout/sign wrong");
            if (received==0) first_tick=data[31:8];
            else if (check_spacing && data[31:8]-previous_tick!=8) $fatal(1,"Wrong sample interval");
            previous_tick=data[31:8]; received=received+1;
            flags_seen=flags_seen | data[111:96];
            if(last) last_seen=last_seen+1;
        end
    end
    task cycles(input integer n); begin repeat(n) @(negedge clk); end endtask
    task arm(input integer frames,input integer tail); begin
        control=0; active=0; ready=1; flags=0; sample_valid=1; cycles(3);
        received=0;last_seen=0;flags_seen=0;check_spacing=1;
        tail_clocks=tail;control=(frames<<8)|(3<<1)|1;cycles(3);
        if (!status[0] || received!=0) $fatal(1,"Not waiting for hardware trigger");
    end endtask
    task finish_check(input integer expected); begin
        cycles(8);
        if(!status[2] || received!=expected || status[31:8]!=expected || last_seen!=1)
            $fatal(1,"Done/count/TLAST wrong: %x frames%0d expected%0d last%0d",status,received,expected,last_seen);
    end endtask
    initial begin
        cycles(4);rst_n=1;cycles(3);
        arm(100,0);cycles(10);active=1;cycles(40);active=0;
        finish_check(5);
        if(status[6:3]!=0) $fatal(1,"Unexpected flags");

        arm(100,16);active=1;cycles(40);active=0;cycles(16);
        finish_check(7);

        arm(100,0);active=1;cycles(1);active=0;finish_check(1);

        arm(3,0);active=1;cycles(40);active=0;finish_check(3);
        if(!status[4]) $fatal(1,"Maximum length did not flag truncated shot");

        arm(100,0);active=1;cycles(2);flags=16'h4;sample_valid=0;cycles(1);
        flags=0;sample_valid=1;cycles(37);active=0;finish_check(5);
        if(!(flags_seen&4) || !status[5]) $fatal(1,"Missed between-sample fault");

        arm(100,0);ready=0;check_spacing=0;active=1;cycles(40);active=0;cycles(8);
        if(!status[3] || status[2]) $fatal(1,"Overflow/backpressure flags wrong");
        ready=1;finish_check(2);

        arm(100,0);active=1;cycles(10);tail_clocks=2;cycles(10);active=0;
        finish_check(3);if(!status[6]) $fatal(1,"Configuration change not flagged");
        $display("PASS: shot trigger, tail, uniform spacing, early TLAST, truncation, overflow, fault capture");
        $finish;
    end
    initial begin #100000; $fatal(1,"Timeout"); end
endmodule
