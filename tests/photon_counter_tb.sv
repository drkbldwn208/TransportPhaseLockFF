`timescale 1ns / 1ps
// Photon PMOD input is asynchronous to 245.76 MHz. 37.5 MHz = 26.667 ns
// between rising edges, already longer than the detector's 23.3 ns dead time.
module photon_counter_tb;
    reg clk=0, gpio_clk=0, rst_n=0, photon_pin=0, trigger_pin=0, ready=1;
    always #2.034505 clk=~clk;
    always #5.137 gpio_clk=~gpio_clk;
    wire edge_pulse, trigger, valid, last;
    wire [31:0] data;
    reg [31:0] nbins=128, ncycles=128;
    pmod_sync_edge sync (.clk(clk),.rst_n(rst_n),.pmod_in(photon_pin),.sync_edge(edge_pulse));
    pmod_debounce_sync trig (.clk(clk),.rst_n(rst_n),.async_pin(trigger_pin),
        .clear_latch(1'b0),.event_pulse(trigger),.debounced_level(),.event_latched());
    hist_counter dut (.clk(clk),.rst_n(rst_n),.gpio_clk(gpio_clk),.gpio_nbins(nbins),
        .gpio_ncycles(ncycles),.trigger(trigger),.input_edge(edge_pulse),
        .m_axis_tdata(data),.m_axis_tvalid(valid),.m_axis_tlast(last),.m_axis_tready(ready));
    integer pulses=0, edges=0, words=0, total=0, done=0, invalid=0;
    integer expected[0:255], bin_index=0, cycle_index=0, count=0;
    reg counting=0, stalled=0;
    reg [32:0] held;
    real previous_rise=-1000.0;
    always @(posedge photon_pin) begin
        if ($realtime-previous_rise<23.299) $fatal(1,"Detector dead time violated");
        previous_rise=$realtime; pulses=pulses+1;
    end
    always @(posedge clk) begin
        if (!rst_n) begin counting=0; bin_index=0;cycle_index=0;count=0;stalled=0;end
        else begin
            if (stalled && {last,data}!==held) $fatal(1,"AXIS data changed under backpressure");
            stalled=valid&&!ready;held={last,data};
            if (edge_pulse) edges=edges+1;
            if (counting) begin
                count=count+edge_pulse;cycle_index=cycle_index+1;
                if (cycle_index==ncycles) begin
                    expected[bin_index]=count;bin_index=bin_index+1;cycle_index=0;count=0;
                    if (bin_index==nbins) counting=0;
                end
            end else if (trigger && !valid) begin counting=1;bin_index=0;end
            if (valid&&ready) begin
                if (data[31]) invalid=invalid+1;
                else begin
                    if (data!==expected[words]) $fatal(1,"Wrong bin %d: %d expected %d",words,data,expected[words]);
                    total=total+data;
                end
                words=words+1;
                if (last) done=1;
            end
        end
    end
    task initialize;
        begin
            rst_n=0;ready=1;trigger_pin=0;photon_pin=0;
            repeat(8) @(negedge clk);
            pulses=0;edges=0;words=0;total=0;done=0;invalid=0;
            rst_n=1;repeat(100) @(negedge gpio_clk);
        end
    endtask
    task trigger_shot;
        begin #1.371;trigger_pin=1;#200;trigger_pin=0;#100;end
    endtask
    real period_ns;
    initial begin
        for (integer trial=0;trial<9;trial=trial+1) begin
            initialize();trigger_shot();
            fork
                begin
                    #(0.511*trial);
                    for (integer p=0;p<1000;p=p+1) begin
                        // Fixed maximum rate and slower irregular arrival trains.
                        period_ns=26.666667+(trial%2 ? $urandom_range(0,10000)/1000.0 : 0.0);
                        // Dead-time-limited pairs, still 37.5 MHz average.
                        if (trial==8) period_ns=(p%2) ? 30.033334 : 23.3;
                        photon_pin=1;#9.9;photon_pin=0;#(period_ns-9.9);
                    end
                end
                begin
                    // Short stalls, including bin boundaries; pending bin held.
                    repeat(100) begin #337.123;ready=0;#83.7;ready=1;end
                end
            join
            wait(done);#40;
            if (total!=1000 || edges!=1000 || pulses!=1000 || words!=128 || invalid) $fatal(1,"Lost/double counts trial %d",trial);
            $display("PASS: photon trial %d, 1000 async pulses, 128 exact bins",trial);
        end
        // Long backpressure must mark an invalid record, never silently drop.
        initialize();trigger_shot();#30;ready=0;#2000;ready=1;wait(done);#20;
        if (invalid!=1) $fatal(1,"Missing overflow marker");
        // Immediate retrigger after the failed record must start cleanly.
        initialize();trigger_shot();wait(done);
        if (total!=0 || words!=128 || invalid) $fatal(1,"Dark capture failed");
        $display("PASS: photon overflow reporting and empty/repeated shots");$finish;
    end
    initial begin #2000000;$fatal(1,"Photon timeout");end
endmodule
