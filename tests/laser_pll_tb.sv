`timescale 1ns/1ps
module laser_pll_tb;
    reg clk=0;
    always #2.034505208 clk=~clk;
    reg rst_n=0, valid=0, ready=1;
    reg [127:0] adc_data=0;
    reg [31:0] low_word=0, high_word=0, control=0, offset=0;
    wire [223:0] dac_data;
    wire dac_valid, adc_ready;
    wire [31:0] phase_status, frequency_status;
    laser_pll dut(.clk(clk), .rst_n(rst_n), .s_axis_tdata(adc_data),
        .s_axis_tvalid(valid), .s_axis_tready(adc_ready), .m_axis_tdata(dac_data),
        .m_axis_tvalid(dac_valid), .m_axis_tready(ready), .frequency_low(low_word),
        .frequency_high(high_word), .control(control), .phase_offset(offset),
        .acquisition_control(32'h00200040), .test_dc(32'b0),
        .acquisition_status(), .fft_status(), .phase_status(phase_status), .frequency_status(frequency_status));
    integer input_file, output_file, count, cycle=0;
    reg [223:0] held_data;
    reg was_stalled=0;
    initial begin
        input_file=$fopen("stimulus.txt", "r");
        output_file=$fopen("output.txt", "w");
        if (!input_file || !output_file) $fatal(1,"Cannot open test files");
        while (!$feof(input_file)) begin
            @(negedge clk);
            count=$fscanf(input_file,"%h %h %h %h %h %h %h %h\n",
                rst_n,valid,ready,adc_data,low_word,high_word,control,offset);
            if (count!=8) $fatal(1,"Malformed stimulus");
            @(posedge clk); #0.1;
            if (rst_n && !adc_ready) $fatal(1,"ADC must never be stalled");
            // Test stability on every stalled clock, with no disable/reset transition.
            if (rst_n && was_stalled && dac_data !== held_data && !ready)
                $fatal(1,"DAC data changed while stalled");
            was_stalled= !ready;
            held_data=dac_data;
            for (integer k=1;k<7;k=k+1)
                if (dac_data[32*k +:32] !== dac_data[31:0]) $fatal(1,"DAC repeat packing");
            if (dac_data[31:16] !== 0) $fatal(1,"DAC Q must be zero");
            $fdisplay(output_file,"%d %h %h %h %h %h", cycle, phase_status,
                frequency_status,dac_data[15:0],dut.mixer.phase_accumulator,dut.mixer.frequency_word);
            cycle=cycle+1;
        end
        $fclose(input_file); $fclose(output_file);
        $display("PASS: streaming and DAC packing assertions (%0d cycles)",cycle);
        $finish;
    end
endmodule
