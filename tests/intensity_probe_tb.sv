`timescale 1ns/1ps
module intensity_probe_tb;
    reg clk=0; always #2 clk=~clk;
    reg rst_n=0, adc_valid=1, dac_ready=1, manual_enable=0, ready=1;
    reg [63:0] adc_bus={16'd400,16'd300,16'd200,16'd100};
    reg signed [15:0] controller_command=12000, manual_command=8000;
    reg [31:0] control=0,frequency_word=32'h01000000,amplitude_word=1000,limits=32'h7fff0000;
    wire [15:0] command_out; wire [31:0] status,version,clips,invalids;
    wire fifo_rst_n,valid,last; wire [127:0] data;
    intensity_probe dut(.clk(clk),.rst_n(rst_n),.adc_bus(adc_bus),.adc_valid(adc_valid),
        .dac_ready(dac_ready),.controller_command(controller_command),.manual_command(manual_command),
        .manual_enable(manual_enable),.command_out(command_out),.control(control),
        .frequency_word(frequency_word),.amplitude_word(amplitude_word),.limits(limits),
        .status(status),.feature_version(version),.clip_samples(clips),.invalid_samples(invalids),
        .fifo_rst_n(fifo_rst_n),.m_axis_tdata(data),.m_axis_tvalid(valid),.m_axis_tlast(last),.m_axis_tready(ready));
    integer records=0, fd, test_number=0;
    real expected, phase, measured;
    always @(posedge clk) if(valid && ready) begin
        records=records+1;
        if(test_number<3 && data[63:0]!==adc_bus) $fatal(1,"ADC lane packing changed");
        if(test_number==1) begin
            phase=$itor(data[127:97])*2.0/4294967296.0*6.283185307179586;
            // Avoid signed conversion of unsigned phase above pi.
            phase=(data[127:96]*1.0)/4294967296.0*6.283185307179586;
            measured=$signed(data[95:80])-$signed(data[79:64]);
            expected=1000*$cos(phase);
            if(measured-expected>2.1 || measured-expected < -2.1) $fatal(1,"DDS/command phase mismatch");
        end
        if(last && records!=32) $fatal(1,"wrong TLAST record");
    end
    task finish_capture;
        begin
            wait(status[1]); @(negedge clk);
            if(records!=32) $fatal(1,"wrong count");
        end
    endtask
    initial begin
        repeat(5) @(negedge clk);rst_n=1;
        @(posedge clk);#1;if(command_out!=12000) $fatal(1,"idle PI boundary");
        @(negedge clk);controller_command=13000;
        #1;if(command_out!=12000) $fatal(1,"missing boundary register");
        @(posedge clk);#1;if(command_out!=13000) $fatal(1,"wrong boundary latency");
        @(negedge clk);manual_enable=1;
        @(posedge clk);#1;if(command_out!=8000) $fatal(1,"manual boundary");
        @(negedge clk);manual_enable=0;controller_command=12000;
        control=1;wait(!status[7] && status[8]);repeat(10) @(negedge clk);
        test_number=1;records=0;control=(32<<12)|(3<<3)|3;
        finish_capture();if(status[6:2]!=0 || status[9]) $fatal(1,"unexpected capture fault");
        control=1;@(negedge clk);records=0;test_number=2;limits={16'd12500,16'd11500};
        control=(32<<12)|(3<<3)|3;
        finish_capture();if(!status[4] || clips==0) $fatal(1,"clip not detected");
        if(command_out<11500 || command_out>12500) $fatal(1,"limits failed");
        control=1;@(negedge clk);records=0;limits=32'h7fff0000;
        control=(32<<12)|(3<<3)|3;
        repeat(12) @(negedge clk);adc_valid=0;@(negedge clk);adc_valid=1;
        finish_capture();if(!status[3] || invalids!=1) $fatal(1,"invalid sample not detected");
        control=1;@(negedge clk);records=0;ready=0;control=(32<<12)|(3<<3)|3;
        repeat(40) @(negedge clk);ready=1;
        finish_capture();if(!status[2]) $fatal(1,"overflow not detected");
        control=1;@(negedge clk);records=0;test_number=3;
        // A rail exactly at the LAST capture clock must survive the diagnostic
        // pipeline; an old rail before the capture must not leak into it.
        adc_bus={4{16'h7ff0}};repeat(2) @(negedge clk);
        adc_bus={16'd400,16'd300,16'd200,16'd100};
        control=(32<<12)|(3<<3)|3;
        wait(dut.count==31 && dut.interval_count==7);@(negedge clk);adc_bus={4{16'h7ff0}};
        wait(!dut.collecting);@(negedge clk);
        adc_bus={16'd400,16'd300,16'd200,16'd100};
        finish_capture();if(!status[6]) $fatal(1,"last ADC rail not detected");
        control=1;@(negedge clk);records=0;
        adc_bus={16'd400,16'd300,16'd200,16'd100};
        repeat(3) @(negedge clk);control=(32<<12)|(3<<3)|3;
        finish_capture();if(status[6]) $fatal(1,"old ADC rail leaked into new capture");
        control=0;wait(!status[8]);repeat(8) @(negedge clk);
        if(command_out!=controller_command || dut.dither!=0) $fatal(1,"tone did not shut off");
        $display("PASS: intensity one-clock boundary, DDS phase, packing, limits, invalid data, backpressure, rail window, ramp down");
        $finish;
    end
    initial begin #5000000;$fatal(1,"timeout");end
endmodule
