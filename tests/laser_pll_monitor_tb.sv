`timescale 1ns/1ps
module laser_pll_monitor_tb;
    reg clk=0;
    always #2 clk=~clk;
    reg rst_n=0, valid=1, ready=1;
    reg signed [23:0] i_data=0, q_data=0;
    reg [31:0] cfg=0;
    wire [31:0] status;
    wire [127:0] data;
    wire out_valid, last, fifo_reset;
    laser_pll_monitor dut(.clk(clk),.rst_n(rst_n),.i_sample(i_data),.q_sample(q_data),
        .sample_valid(valid),.monitor_control(cfg),.monitor_status(status),
        .fifo_rst_n(fifo_reset),.m_axis_tdata(data),.m_axis_tvalid(out_valid),
        .m_axis_tready(ready),.m_axis_tlast(last));
    task tick; begin @(posedge clk); #0.1; end endtask
    reg [127:0] held;
    reg held_last;
    integer received, sample_number, last_count;
    longint sum_i, sum_q, expected_i[0:31], expected_q[0:31];
    initial begin
        repeat(4) tick; @(negedge clk); rst_n=1;
        // Means for ramping signed I/Q, including negative fractional rounding.
        for (integer d=0;d<=4;d=d+1) begin
            @(negedge clk); cfg=0;
            tick;
            @(negedge clk); cfg=(20<<12)|(d<<1)|1;
            tick;
            received=0; sample_number=0; last_count=0; sum_i=0; sum_q=0;
            while (!status[1]) begin
                @(negedge clk);
                i_data=sample_number*3-500; q_data=1000-sample_number*2;
                if (sample_number < (20<<d)) begin
                    sum_i=sum_i+i_data; sum_q=sum_q+q_data;
                    if ((sample_number % (1<<d))==((1<<d)-1)) begin
                        expected_i[sample_number>>d]=sum_i>>>d;
                        expected_q[sample_number>>d]=sum_q>>>d;
                        sum_i=0; sum_q=0;
                    end
                end
                if (out_valid && ready) begin
                    if ($signed(data[127:64])!=expected_i[received] ||
                        $signed(data[63:0])!=expected_q[received]) $fatal(1,"IQ averaging/packing d=%d",d);
                    if (last!=(received==19)) $fatal(1,"TLAST sample count");
                    if (last) last_count=last_count+1;
                    received=received+1;
                end
                tick; sample_number=sample_number+1;
                if (sample_number>(20<<d)+10) $fatal(1,"Capture did not finish");
            end
            if (received!=20 || last_count!=1 || status[3:2]!=0) $fatal(1,"Capture flags/count");
            repeat(10) tick;
            if (out_valid || status[31:12]!=20) $fatal(1,"Capture repeated without rearming");
        end
        // Stall longer than output buffer; AXIS must hold and loss must be flagged.
        @(negedge clk); cfg=0; tick;
        @(negedge clk); cfg=(4<<12)|1; ready=0; i_data=100; q_data=-200;
        repeat(3) tick; held=data; held_last=last;
        repeat(20) begin
            @(negedge clk); i_data=i_data+1; tick;
            if (data!==held || last!==held_last || !out_valid) $fatal(1,"AXIS changed during backpressure");
        end
        if (!status[2]) $fatal(1,"Lost samples were not flagged");
        @(negedge clk); ready=1;
        repeat(10) tick;
        if (!status[1] || status[31:12]!=4) $fatal(1,"Stalled packet did not complete");
        // Invalid source has explicit zero sample/flag, not compressed timestamps.
        @(negedge clk); cfg=0; tick;
        @(negedge clk); cfg=(1<<12)|1; valid=0;
        repeat(2) tick;
        if (!out_valid || data!=0 || !last || !status[3]) $fatal(1,"Invalid sample semantics");
        tick;
        // Largest supported average cannot overflow with full-scale signed input.
        @(negedge clk); cfg=0; valid=1; tick;
        @(negedge clk); cfg=(1<<12)|(16<<1)|1; i_data=24'sh7fffff; q_data=24'sh800000;
        repeat(65537) tick;
        if (!out_valid || $signed(data[127:64])!=8388607 || $signed(data[63:0])!=-8388608)
            $fatal(1,"Full-scale 65536-sample average overflow");
        tick;
        @(negedge clk); cfg=0;
        tick; if (fifo_reset || out_valid || status!=0) $fatal(1,"Monitor/FIFO reset");
        $display("PASS: I/Q signed means, packing, lengths/TLAST, independent arm, backpressure/loss flags, invalid samples, full-scale /65536");
        $finish;
    end
endmodule
