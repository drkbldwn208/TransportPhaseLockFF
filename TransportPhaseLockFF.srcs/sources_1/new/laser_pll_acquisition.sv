`timescale 1ns / 1ps
// Parallel coarse/fine detector selection. No NCO retuning and no loop filter.
module laser_pll_acquisition (
    input wire clk,
    input wire rst_n,
    input wire ready,
    input wire [31:0] acquisition_control,
    input wire [31:0] test_dc,
    input wire [31:0] control,
    input wire [47:0] reference_frequency,
    input wire [9:0] fft_bin,
    input wire fft_valid,
    input wire error_valid,
    input wire signed [15:0] legacy_target,
    input wire legacy_saturated,
    input wire signed [15:0] capture_target,
    input wire capture_saturated,
    input wire signed [15:0] unwrapped_target,
    input wire unwrapped_saturated,
    input wire unwrapped_valid,
    input wire signed [15:0] tracking_target,
    input wire tracking_saturated,
    input wire tracking_valid,
    input wire target_valid,
    input wire signed [23:0] turns,
    output wire unwrap_arm,
    output wire tracking_arm,
    output wire signed [15:0] dac_target,
    output wire output_valid,
    output wire output_saturated,
    output wire [31:0] acquisition_status
);
    // Mode 0 retains the old wrapped detector for comparison; 1/2/3 are stages.
    // Mode 4 is tracking; bit 3 requests it. Bit 2 overrides with DC (mode 5).
    wire [2:0] request = acquisition_control[2] ? 3'd5 :
                         acquisition_control[3] ? 3'd4 : {1'b0,acquisition_control[1:0]};
    wire [2:0] active_mode;
    wire transitioning;
    // Frequency codes are turns per fabric clock, as in the fine discriminator,
    // but widened so +/-600 MHz does not wrap at +/-122.88 MHz.
    reg signed [21:0] coarse_frequency_error;
    reg signed [37:0] coarse_scaled;
    wire signed [37:0] coarse_dac = (control[2] ? -coarse_scaled : coarse_scaled) >>> 2;
    reg coarse_valid1, coarse_valid2;
    always @(posedge clk) begin
        coarse_frequency_error <= $signed({1'b0,reference_frequency[47:27]}) -
                                  $signed({1'b0,fft_bin,11'b0});
        coarse_scaled <= $signed({{16{coarse_frequency_error[21]}},coarse_frequency_error})
                         <<< acquisition_control[11:8];
        coarse_valid1 <= rst_n && fft_valid;
        coarse_valid2 <= rst_n && coarse_valid1;
    end
    wire signed [15:0] coarse_target = coarse_dac>32767 ? 16'sh7fff :
                                     coarse_dac < -32768 ? 16'sh8000 : coarse_dac[15:0];
    wire coarse_saturated = coarse_dac>32767 || coarse_dac < -32768;
    // 80 MHz leaves margin inside the +/-100 MHz tested DDC range.
    wire near_ready = coarse_valid2 && fft_valid && target_valid &&
                      coarse_frequency_error < 22'sd85333 && coarse_frequency_error > -22'sd85333;
    // Stage 3 is manual: no frequency-band, FFT or dwell qualification.
    // Valid fine data and wrap-memory preparation are still needed for handoff.
    wire fine_ready = error_valid && target_valid;
    reg [4:0] unwrap_prepared;
    // Start memory before switching the output, so a crossing at entry cannot
    // reach the DAC as an uncounted +/-pi jump through the error pipeline.
    assign unwrap_arm = active_mode==3 || active_mode==4 ||
                        ((request==3 || request==4) && fine_ready);
    assign tracking_arm = active_mode==4 || request==4;
    always @(posedge clk) begin
        if (!rst_n || !unwrap_arm || !target_valid) unwrap_prepared <= 0;
        else unwrap_prepared <= {unwrap_prepared[3:0],1'b1};
    end
    reg signed [15:0] active_target, requested_target;
    reg active_valid, requested_valid, active_saturated;
    reg request_allowed;
    // Two small muxes allow the old detector to keep running during a request.
    always @* begin
        active_target=legacy_target; active_valid=target_valid; active_saturated=legacy_saturated;
        case (active_mode)
            1: begin active_target=coarse_target; active_valid=coarse_valid2 && fft_valid; active_saturated=coarse_saturated; end
            2: begin active_target=capture_target; active_saturated=capture_saturated; end
            3: begin active_target=unwrapped_target; active_valid=unwrapped_valid; active_saturated=unwrapped_saturated; end
            4: begin active_target=tracking_target; active_valid=tracking_valid; active_saturated=tracking_saturated; end
            5: begin active_target=test_dc[15:0]; active_valid=1; active_saturated=0; end
        endcase
        requested_target=legacy_target; requested_valid=target_valid;
        request_allowed=1;
        case (request)
            1: begin requested_target=coarse_target; requested_valid=coarse_valid2 && fft_valid; end
            2: begin requested_target=capture_target; request_allowed=near_ready; end
            3: begin requested_target=unwrapped_target; requested_valid=unwrapped_valid;
                     request_allowed=fine_ready && unwrap_prepared[4]; end
            4: begin requested_target=tracking_target; requested_valid=tracking_valid;
                     request_allowed=fine_ready && unwrap_prepared[4]; end
            5: begin requested_target=test_dc[15:0]; requested_valid=1; end
        endcase
    end
    laser_pll_handoff handoff (.clk(clk), .rst_n(rst_n), .ready(ready),
        .requested_mode(request), .request_allowed(request_allowed),
        .ramp_interval_log2(acquisition_control[7:4]),
        .requested_target(requested_target), .requested_valid(requested_valid),
        .active_target(active_target),
        .active_valid(active_valid), .active_saturated(active_saturated),
        .active_mode(active_mode), .dac_target(dac_target), .target_valid(output_valid),
        .target_saturated(output_saturated), .transitioning(transitioning));
    assign acquisition_status = {turns,output_valid,fine_ready,near_ready,
                                 (request!=active_mode),transitioning,active_mode};
endmodule
