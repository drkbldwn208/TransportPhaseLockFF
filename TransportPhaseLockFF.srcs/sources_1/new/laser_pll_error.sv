`timescale 1ns / 1ps
// Phase detector and optional frequency discriminator; no feedback controller.
// All phase quantities are signed 18-bit turns (2^18 codes = 2*pi radians).
module laser_pll_error (
    input wire clk,
    input wire rst_n,
    input wire signed [17:0] measured_phase,
    input wire phase_valid,
    input wire [31:0] control,
    input wire [31:0] phase_offset,
    output reg signed [17:0] phase_error,
    output reg signed [17:0] frequency_error,
    output reg error_valid,
    output wire signed [15:0] dac_target,
    output reg target_valid,
    output wire target_saturated
);
    wire signed [17:0] error_now = phase_offset[17:0] - measured_phase;
    reg signed [17:0] previous_phase;
    wire signed [17:0] delta_now = previous_phase - measured_phase;
    reg previous_valid;
    reg signed [48:0] combined_error;
    wire signed [48:0] phase_wide = {{31{phase_error[17]}},phase_error};
    wire signed [48:0] frequency_wide = {{31{frequency_error[17]}},frequency_error};
    wire signed [48:0] combined_now = phase_wide +
        (control[1] ? (frequency_wide <<< control[11:8]) : 49'sd0);
    wire signed [48:0] scaled_error = (control[2] ? -combined_error : combined_error) >>> 2;

    // No accumulation of turns: the wrapped difference is unambiguous for
    // |f_input-f_ref| < 122.88 MHz when valid samples are consecutive.
    always @(posedge clk) begin
        if (!rst_n) begin
            previous_phase <= 0;
            previous_valid <= 0;
            phase_error <= 0;
            frequency_error <= 0;
            error_valid <= 0;
            combined_error <= 0;
            target_valid <= 0;
        end else begin
            previous_valid <= phase_valid;
            error_valid <= phase_valid;
            if (phase_valid) begin
                previous_phase <= measured_phase;
                phase_error <= error_now;
                frequency_error <= previous_valid ? delta_now : 18'sd0;
            end
            combined_error <= combined_now <<< control[7:4];
            target_valid <= error_valid;
        end
    end
    // 49 bits preserve sign even at both maximum GPIO gain settings.
    assign target_saturated = scaled_error > 32767 || scaled_error < -32768;
    assign dac_target = scaled_error > 32767 ? 16'sh7fff :
                        scaled_error < -32768 ? 16'sh8000 : scaled_error[15:0];
endmodule
