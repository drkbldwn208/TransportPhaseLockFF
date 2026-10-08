`timescale 1ns/1ps
// Real error + acquisition blocks: cross the atan2 branch cut during handoff.
module laser_pll_fine_entry_tb;
    reg clk=0;
    always #2 clk=~clk;
    reg rst_n=0;
    reg signed [17:0] measured_phase=0;
    reg [31:0] cfg=32'h00200002;
    reg [9:0] fft_bin=417;
    reg fft_valid=1;
    wire signed [17:0] phase_error, frequency_error;
    wire signed [15:0] legacy, capture, unwrapped, dac;
    wire valid, target_valid, legacy_sat, capture_sat, unwrapped_sat, unwrapped_valid, arm, output_valid;
    wire signed [23:0] turns;
    wire [31:0] status;
    laser_pll_error detector(.clk(clk),.rst_n(rst_n),.measured_phase(measured_phase),
        .phase_valid(rst_n),.control(32'h00000607),.phase_offset(32'd0),.unwrap_arm(arm),
        .phase_error(phase_error),.frequency_error(frequency_error),.error_valid(valid),
        .dac_target(legacy),.target_valid(target_valid),.target_saturated(legacy_sat),
        .capture_target(capture),.capture_saturated(capture_sat),
        .unwrapped_target(unwrapped),.unwrapped_saturated(unwrapped_sat),.unwrapped_valid(unwrapped_valid),.turns(turns));
    laser_pll_acquisition acquisition(.clk(clk),.rst_n(rst_n),.ready(1'b1),
        .acquisition_control(cfg),.test_dc(32'd0),.control(32'h00000607),
        .reference_frequency(48'd114532461226667),.fft_bin(fft_bin),.fft_valid(fft_valid),
        .error_valid(valid),
        .legacy_target(legacy),.legacy_saturated(legacy_sat),
        .capture_target(capture),.capture_saturated(capture_sat),
        .unwrapped_target(unwrapped),.unwrapped_saturated(unwrapped_sat),
        .unwrapped_valid(unwrapped_valid),
        .target_valid(target_valid),.turns(turns),.unwrap_arm(arm),
        .dac_target(dac),.output_valid(output_valid),.output_saturated(),.acquisition_status(status));
    integer previous, delta, base, phase_step, maximum_step;
    reg previously_fine;
    initial begin
        // FFT becomes invalid or far away at entry: it must not veto stage 3.
        // 93.75 kHz, approximately 10 MHz, 20 MHz and 100 MHz detuning.
        for (integer rate=0;rate<4;rate=rate+1) begin
        phase_step=rate==0 ? 100 : rate==1 ? 10667 : rate==2 ? 21333 : 106667;
        maximum_step=(phase_step+639)/640+2; // /160 slope, rounding and offset decay
        for (integer initial_stage=0;initial_stage<=2;initial_stage=initial_stage+2) begin
        for (integer direction=-1;direction<=1;direction=direction+2) begin
            for (integer crossing=-4;crossing<=4;crossing=crossing+1) begin
                @(negedge clk); rst_n=0; cfg=32'h00200000 | initial_stage; previously_fine=0;
                fft_valid=1; fft_bin=417; // permit initial stage 2 before disabling its FFT guard
                repeat(4) @(posedge clk);
                base=direction*(131072+crossing*phase_step-100*phase_step);
                for (integer k=0;k<2100;k=k+1) begin
                    @(negedge clk);
                    rst_n=1; measured_phase=-(base+direction*k*phase_step);
                    if (k==100) begin cfg=32'h00200003; fft_valid=crossing>=0; fft_bin=104; end
                    previous=dac;
                    @(posedge clk); #0.1;
                    if (k==90 && status[2:0]!=initial_stage) $fatal(1,"Initial stage was not entered");
                    // Allow pipeline history near the +/-80-turn rail. Multiple
                    // remembered turns inside that range must remain linear.
                    if (unwrapped_valid && (turns>82 || turns < -82) && !unwrapped_sat)
                        $fatal(1,"Large unwrapped error must report DAC saturation");
                    if (status[2:0]==3) begin
                        delta=$signed(dac)-previous;
                        if (!previously_fine && delta!=0) $fatal(1,"Entry discontinuity %d",delta);
                        if (previously_fine && (delta>maximum_step || delta < -maximum_step))
                            $fatal(1,"Uncounted branch cut near handoff: dir=%d crossing=%d k=%d delta=%d",direction,crossing,k,delta);
                        previously_fine=1;
                    end
                end
                if (!previously_fine) $fatal(1,"Fine entry never accepted");
            end
        end
        end
        end
        $display("PASS: manual fine entry without FFT; both signs; 9 wrap alignments; 93.75 kHz / 10 MHz / 20 MHz / 100 MHz detuning");
        $finish;
    end
endmodule
