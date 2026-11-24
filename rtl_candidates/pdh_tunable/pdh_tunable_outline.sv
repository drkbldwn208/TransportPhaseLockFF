`timescale 1ns / 1ps
// Standalone outline: external CORDIC ports deliberately keep vendor IP and
// the existing BD untouched. See README for IP settings and register map.
module pdh_tunable_outline (
    input wire clk, rst_n,
    input wire cfg_write, cfg_commit,
    input wire [6:0] cfg_address,
    input wire [31:0] cfg_data,
    output wire cfg_busy,
    output reg cfg_ack, fault,
    output wire phase_valid, phase_bank,
    output wire signed [25:0] carrier_angle, modulation_angle,
    input wire carrier_valid, modulation_valid, carrier_bank, modulation_bank,
    input wire signed [23:0] carrier_cos, carrier_sin, modulation_cos, modulation_sin,
    output wire [223:0] sum_data,
    output wire [127:0] reference_data,
    output wire sum_valid, reference_valid,
    input wire sum_ready, reference_ready
);
    // Two small register banks. Only the inactive bank can be written. TUSER
    // accompanies each phase through CORDIC, selecting its original bank.
    reg signed [17:0] coefficients[0:143];
    reg [47:0] frame_increment[0:1];
    reg [1:0] enables[0:1];
    reg active_bank, stream_started;
    reg [75:0] loaded;
    wire sample_valid=carrier_valid && modulation_valid && (carrier_bank==modulation_bank);
    wire apply_config=cfg_commit && !cfg_write && !cfg_busy && (&loaded) && !fault;
    wire clipped, stalled;
    wire [1295:0] selected_coefficients;
    assign cfg_busy=active_bank!=cfg_ack;
    assign phase_bank=active_bank;
    assign phase_valid=rst_n;
    assign sum_valid=rst_n;
    assign reference_valid=rst_n;
    for (genvar k=0;k<72;k=k+1) begin : select_coefficients
        assign selected_coefficients[18*k+:18]=coefficients[carrier_bank ? 72+k : k];
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            active_bank<=0; cfg_ack<=0; fault<=0; stream_started<=0;
            loaded<=76'd8; // Reserved word 3 does not need writing.
            frame_increment[0]<=0; frame_increment[1]<=0;
            enables[0]<=0; enables[1]<=0;
            for (integer k=0;k<144;k=k+1) coefficients[k]<=0;
        end else begin
            if (cfg_write) begin
                if (cfg_busy || cfg_commit || cfg_address>75 || cfg_address==3) fault<=1;
                else begin
                    loaded[cfg_address]<=1;
                    case (cfg_address)
                        0: frame_increment[!active_bank][31:0]<=cfg_data;
                        1: frame_increment[!active_bank][47:32]<=cfg_data[15:0];
                        2: enables[!active_bank]<=cfg_data[1:0];
                        default: coefficients[(!active_bank)*72+cfg_address-4]<=cfg_data[17:0];
                    endcase
                end
            end
            if (cfg_commit && !apply_config) fault<=1;
            if (apply_config) begin
                active_bank<=!active_bank;
                loaded<=76'd8;
            end
            // Old coefficients have reached DSP input registers by this edge;
            // their bank can now be reused, without waiting for DAC output.
            if (sample_valid) begin
                cfg_ack<=carrier_bank;
                stream_started<=1;
            end
            if ((carrier_valid!=modulation_valid) ||
                (carrier_valid && modulation_valid && carrier_bank!=modulation_bank) ||
                (stream_started && !sample_valid) || clipped || stalled) fault<=1;
        end
    end

    pdh_phase_source phases (
        .clk(clk), .rst_n(rst_n), .apply_frequency(apply_config),
        .requested_frame_increment(frame_increment[!active_bank]),
        .carrier_angle(carrier_angle), .modulation_angle(modulation_angle)
    );
    pdh_parallel_rotations rotations (
        .clk(clk), .rst_n(rst_n), .valid(sample_valid), .enable(enables[carrier_bank]),
        .carrier_cos(carrier_cos), .carrier_sin(carrier_sin),
        .modulation_cos(modulation_cos), .modulation_sin(modulation_sin),
        .coefficients(selected_coefficients), .fault(fault),
        .sum_data(sum_data), .reference_data(reference_data),
        .sum_ready(sum_ready), .reference_ready(reference_ready),
        .clipped(clipped), .stalled(stalled)
    );
endmodule
