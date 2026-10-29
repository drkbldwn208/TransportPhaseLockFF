`timescale 1ns / 1ps
// Plain Verilog boundary for Vivado module-reference inference.
module intensity_linearized_wrapper (
    (* X_INTERFACE_PARAMETER="ASSOCIATED_RESET rst_n" *) input wire clk,
    (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input wire rst_n,
    input wire adc_valid,shot_active,
    input wire [63:0] adc_bus,
    input wire [15:0] reference_in,legacy_command,
    input wire [31:0] control,write_address,write_data,
    output wire [31:0] status,read_data,feature_version,
    output wire [15:0] command_out,reference_power,measured_power,
    output wire signed [31:0] error_q8,
    output wire signed [15:0] raw_adc,
    output wire [15:0] sample_flags
);
    intensity_linearized core(.clk(clk),
        .rst_n(rst_n),
        .adc_valid(adc_valid),
        .shot_active(shot_active),
        .adc_bus(adc_bus),
        .reference_in(reference_in),
        .legacy_command(legacy_command),
        .control(control),
        .write_address(write_address),
        .write_data(write_data),
        .status(status),
        .read_data(read_data),
        .feature_version(feature_version),
        .command_out(command_out),
        .reference_power(reference_power),
        .measured_power(measured_power),
        .error_q8(error_q8),
        .raw_adc(raw_adc),
        .sample_flags(sample_flags));
endmodule
