`timescale 1ns / 1ps
// Candidate only: not part of the open Vivado project.
// One carrier phase per 14-sample word, and one shared exact 60 MHz phase.
module pdh_phase_source (
    input wire clk, rst_n,
    input wire apply_frequency,
    input wire [47:0] requested_frame_increment,
    output wire signed [25:0] carrier_angle, modulation_angle
);
    reg [47:0] carrier_phase, frame_increment;
    reg [8:0] modulation_frame;
    // AMD CORDIC scaled radians: signed 26-bit Q23 represents angle/pi.
    // Thus 24 bits span a complete turn. Round the 48-bit phase first.
    wire [47:0] rounded_carrier=carrier_phase+48'd8388608;
    wire [47:0] modulation_phase={modulation_frame,39'd0};
    assign carrier_angle={{2{rounded_carrier[47]}},rounded_carrier[47:24]};
    assign modulation_angle={{2{modulation_phase[47]}},modulation_phase[47:24]};

    always @(posedge clk) begin
        if (!rst_n) begin
            carrier_phase<=0; frame_increment<=0; modulation_frame<=0;
        end else begin
            // Advance through the old word before adopting the new slope.
            // Frequency changes NEVER reset the accumulated phase.
            carrier_phase<=carrier_phase+frame_increment;
            modulation_frame<=modulation_frame+9'd125; // 60/245.76 = 125/512.
            if (apply_frequency) frame_increment<=requested_frame_increment;
        end
    end
endmodule
