`timescale 1ns/1ps
// Real error + acquisition blocks: cross the atan2 branch cut during handoff.
module laser_pll_fine_entry_tb;
    reg clk=0;
    always #2 clk=~clk;
    reg rst_n=0;
    reg signed [17:0] measured_phase=0;
    reg [31:0] cfg=32'h00200002;
    wire signed [17:0] phase_error, frequency_error;
    wire signed [15:0] legacy, capture, unwrapped, dac;
    wire valid, target_valid, legacy_sat, capture_sat, unwrapped_sat, arm, output_valid;
    wire signed [23:0] turns;
    wire [31:0] status;
    laser_pll_error detector(.clk(clk),.rst_n(rst_n),.measured_phase(measured_phase),
        .phase_valid(rst_n),.control(32'h00000607),.phase_offset(32'd0),.unwrap_arm(arm),
        .phase_error(phase_error),.frequency_error(frequency_error),.error_valid(valid),
        .dac_target(legacy),.target_valid(target_valid),.target_saturated(legacy_sat),
        .capture_target(capture),.capture_saturated(capture_sat),
        .unwrapped_target(unwrapped),.unwrapped_saturated(unwrapped_sat),.turns(turns));
    laser_pll_acquisition acquisition(.clk(clk),.rst_n(rst_n),.ready(1'b1),
        .acquisition_control(cfg),.test_dc(32'd0),.control(32'h00000607),
        .reference_frequency(48'd114532461226667),.fft_bin(10'd417),.fft_valid(1'b1),
        .frequency_error(frequency_error),.error_valid(valid),
        .legacy_target(legacy),.legacy_saturated(legacy_sat),
        .capture_target(capture),.capture_saturated(capture_sat),
        .unwrapped_target(unwrapped),.unwrapped_saturated(unwrapped_sat),
        .target_valid(target_valid),.turns(turns),.unwrap_arm(arm),
        .dac_target(dac),.output_valid(output_valid),.output_saturated(),.acquisition_status(status));
    integer previous, delta, base;
    reg previously_fine;
    initial begin
        for (integer initial_stage=0;initial_stage<=2;initial_stage=initial_stage+2) begin
        for (integer direction=-1;direction<=1;direction=direction+2) begin
            for (integer crossing=-4;crossing<=4;crossing=crossing+1) begin
                @(negedge clk); rst_n=0; cfg=32'h00200000 | initial_stage; previously_fine=0;
                repeat(4) @(posedge clk);
                base=direction*(131072+crossing*100-4500*100);
                for (integer k=0;k<6500;k=k+1) begin
                    @(negedge clk);
                    rst_n=1; measured_phase=-(base+direction*k*100);
                    if (k==4500) cfg=32'h00200003;
                    previous=dac;
                    @(posedge clk); #0.1;
                    if (target_valid && turns!=0 && !unwrapped_sat)
                        $fatal(1,"Nonzero turn count must report DAC saturation");
                    if (status[2:0]==3) begin
                        delta=$signed(dac)-previous;
                        if (!previously_fine && delta!=0) $fatal(1,"Entry discontinuity %d",delta);
                        if (previously_fine && (delta>26 || delta < -26))
                            $fatal(1,"Uncounted branch cut near handoff: dir=%d crossing=%d k=%d delta=%d",direction,crossing,k,delta);
                        previously_fine=1;
                    end
                end
                if (!previously_fine) $fatal(1,"Fine entry never accepted");
            end
        end
        end
        $display("PASS: legacy 0 and stage 2 -> stage 3; both crossing directions at nine phase-wrap alignments");
        $finish;
    end
endmodule
