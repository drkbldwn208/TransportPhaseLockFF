`timescale 1ns/1ps
// Real ADC tones -> vendor FFT + DDC -> all acquisition stages -> packed DAC.
// Faster (one code/clock) handoff decay shortens simulation, not fast-path delay.
module laser_pll_stages_tb;
    reg clk=0;
    always #2.034505208 clk=~clk;
    reg rst_n=0, adc_valid=0;
    reg [127:0] adc_data=0;
    reg [31:0] control=32'h00400604, acquisition_control=32'h00200001, test_dc=0, tracking_control=0, monitor_control=0;
    localparam [47:0] FCW=48'd114532461226667;
    wire [223:0] dac_data;
    wire [31:0] tracking_status, monitor_status;
    wire [127:0] monitor_data;
    wire monitor_valid, monitor_last;
    integer monitor_received=0;
    wire [31:0] phase_status, frequency_status, acquisition_status, fft_status;
    laser_pll dut(.clk(clk),.rst_n(rst_n),.s_axis_tdata(adc_data),
        .s_axis_tvalid(adc_valid),.s_axis_tready(),.m_axis_tdata(dac_data),
        .m_axis_tvalid(),.m_axis_tready(1'b1),.frequency_low(FCW[31:0]),
        .frequency_high({15'b0,1'b1,FCW[47:32]}),.control(control),.phase_offset(32'b0),
        .tracking_control(tracking_control), .monitor_control(monitor_control), .m_monitor_tready(1'b1),
        .tracking_status(tracking_status), .monitor_status(monitor_status),
        .m_monitor_tdata(monitor_data), .m_monitor_tvalid(monitor_valid), .m_monitor_tlast(monitor_last),
        .acquisition_control(acquisition_control),.test_dc(test_dc),
        .phase_status(phase_status),.frequency_status(frequency_status),
        .acquisition_status(acquisition_status),.fft_status(fft_status));
    real frequency_hz, phase_rad=0.37;
    integer sample_value, previous_target, previous_mode, phase_code, expected_dac;
    initial begin
        for (integer cycle=0;cycle<220020;cycle=cycle+1) begin
            @(negedge clk);
            rst_n=cycle>=4; adc_valid=cycle>=4 && cycle<190000;
            if (cycle==8) control[0]=1;
            frequency_hz=cycle<50000 ? 200e6 : cycle<100000 ? 750e6 : 800e6;
            for (integer lane=0;lane<8;lane=lane+1) begin
                sample_value=$rtoi(20000*$cos(phase_rad));
                adc_data[16*lane +:16]=sample_value;
                phase_rad=phase_rad+6.283185307179586*frequency_hz/1966080000.0;
                if (phase_rad>6.283185307179586) phase_rad=phase_rad-6.283185307179586;
            end
            if (cycle==75000) acquisition_control[1:0]=2;
            if (cycle==85000) acquisition_control[1:0]=3;
            // Re-enter after centering the source to check local phase scaling.
            if (cycle==102000) acquisition_control[1:0]=2;
            if (cycle==120000) acquisition_control[1:0]=3;
            if (cycle==170000) acquisition_control[3]=1;
            if (cycle==175000) tracking_control=3;
            if (cycle==180000) monitor_control=(256<<12)|(4<<1)|1;
            if (cycle==190000) begin acquisition_control[2]=1; test_dc=12000; end
            if (cycle==220000) test_dc=-12000;
            if (cycle==220010) control[0]=0;
            if (monitor_valid) begin
                if (monitor_last!=(monitor_received==255)) $fatal(1,"Integrated monitor TLAST");
                monitor_received=monitor_received+1;
            end
            previous_target=$signed(dut.output_target); previous_mode=acquisition_status[2:0];
            @(posedge clk); #0.1;
            if (rst_n && control[0] && acquisition_status[2:0]!=previous_mode &&
                $signed(dut.output_target)!=previous_target) $fatal(1,"Mode-entry output step");
            for (integer lane=0;lane<7;lane=lane+1)
                if (dac_data[32*lane +:32] !== {16'b0,dac_data[15:0]}) $fatal(1,"DAC packing");
            if (cycle==49000 && (acquisition_status[2:0]!=1 || !fft_status[10] ||
                $signed(dac_data[15:0])!=-32768)) $fatal(1,"200 MHz coarse capture sign/rail");
            // The old coarse output is about -13142 codes. Allow the ~19626
            // one-code steps needed to reach the stage-2 negative rail.
            if (cycle==84000 && (acquisition_status[2:0]!=2 || !phase_status[19] ||
                $signed(dac_data[15:0])>=0)) $fatal(1,"750 MHz near capture stage/sign");
            if (cycle==99000 && (acquisition_status[2:0]!=3 || acquisition_status[4] ||
                $signed(acquisition_status[31:8])<1000))
                $fatal(1,"Manual entry at +50 MHz ref-minus-beat did not accumulate turns");
            if (cycle==101000 && $signed(acquisition_status[31:8])<1000)
                $fatal(1,"Centering the beat silently erased remembered turns");
            // After deliberate re-entry at zero detuning, allow the offset ramp.
            if (cycle==169000) begin
                if (acquisition_status[2:0]!=3 || acquisition_status[4:3]!=0 ||
                    acquisition_status[31:8]!=0 || !phase_status[19]) $fatal(1,"Fine stage did not settle");
                phase_code=$signed(phase_status[17:0]);
                expected_dac=$rtoi($floor(-phase_code/640.0+0.5));
                if ($signed(dac_data[15:0])-expected_dac>4 ||
                    $signed(dac_data[15:0])-expected_dac < -4) $fatal(1,"Fine phase-to-DAC scaling");
            end
            if (cycle==189000) begin
                if (acquisition_status[2:0]!=4 || acquisition_status[4:3]!=0 ||
                    !tracking_status[28] || tracking_status[30] || tracking_status[25:0]!=(104858<<3))
                    $fatal(1,"Integrated tracking did not settle");
                if (monitor_received!=256 || monitor_status[3:0]!=2 || monitor_status[31:12]!=256)
                    $fatal(1,"Integrated monitor incomplete/invalid");
                if (phase_status[20] || !phase_status[19]) $fatal(1,"IQ capture disturbed detector");
            end
            if (cycle==219000 && (acquisition_status[2:0]!=5 || !acquisition_status[7] ||
                phase_status[19] || fft_status[10] || $signed(dac_data[15:0])!=12000))
                $fatal(1,"DC bypass depends on ADC validity or polarity");
            if (cycle==220004 && $signed(dac_data[15:0])!=-12000) $fatal(1,"Negative DC code");
            if (cycle==220014 && dac_data!=0) $fatal(1,"Final mute");
        end
        $display("PASS: real tones 200/750/800 MHz; manual fine entry at 50 MHz; retained turns; continuous handoffs; stage-4 ramp; IQ capture; no-ADC DC; final mute");
        $finish;
    end
endmodule
