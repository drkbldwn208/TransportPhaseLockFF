`timescale 1ns/1ps
module laser_pll_fft_tb;
    reg clk=0;
    always #2.034505208 clk=~clk;
    reg rst_n=0, adc_valid=0;
    reg [127:0] adc_data=0;
    wire [9:0] peak_bin;
    wire estimate_valid;
    wire [31:0] status;
    laser_pll_fft dut(.clk(clk),.rst_n(rst_n),.adc_data(adc_data),.adc_valid(adc_valid),
        .minimum_peak(16'd32),.peak_bin(peak_bin),.estimate_valid(estimate_valid),.fft_status(status));
    integer input_file, output_file, count, cycle=0, scenario;
    reg [7:0] last_frame=0;
    initial begin
        input_file=$fopen("fft_stimulus.txt","r");
        output_file=$fopen("fft_output.txt","w");
        if (!input_file || !output_file) $fatal(1,"FFT files missing");
        while (!$feof(input_file)) begin
            @(negedge clk);
            count=$fscanf(input_file,"%d %h %h %h\n",scenario,rst_n,adc_valid,adc_data);
            if (count!=4) $fatal(1,"Bad FFT vector");
            @(posedge clk); #0.1;
            if (!rst_n) last_frame=0;
            else if (status[23:16]!=last_frame) begin
                $fdisplay(output_file,"%d %d %d %h %d %d",scenario,cycle,peak_bin,status,
                          dut.peak_power,dut.band_power);
                last_frame=status[23:16];
            end
            if (rst_n && !adc_valid && estimate_valid) $fatal(1,"Stale FFT survives ADC gap");
            cycle=cycle+1;
        end
        $fclose(input_file); $fclose(output_file); $finish;
    end
endmodule
