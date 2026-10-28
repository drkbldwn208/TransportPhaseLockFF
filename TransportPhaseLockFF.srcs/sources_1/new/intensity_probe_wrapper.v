`timescale 1ns / 1ps
// Verilog boundary for Vivado module-reference inference.
module intensity_probe_wrapper (
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF m_axis, ASSOCIATED_RESET rst_n:fifo_rst_n" *)
    input wire clk,
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *) input wire rst_n,
    input wire [63:0] adc_bus, adc_rail_bus,
    input wire adc_valid, dac_ready,
    input wire signed [15:0] controller_command, manual_command,
    input wire manual_enable,
    output wire [15:0] command_out,
    input wire [31:0] control, frequency_word, amplitude_word, limits,
    output wire [31:0] status, feature_version,
    output wire [31:0] clip_samples, invalid_samples,
    output wire fifo_rst_n,
    output wire [127:0] m_axis_tdata,
    output wire m_axis_tvalid, m_axis_tlast,
    input wire m_axis_tready
);
    intensity_probe probe (
        .clk(clk),
        .rst_n(rst_n),
        .adc_bus(adc_bus),
        .adc_rail_bus(adc_rail_bus),
        .adc_valid(adc_valid),
        .dac_ready(dac_ready),
        .controller_command(controller_command),
        .manual_command(manual_command),
        .manual_enable(manual_enable),
        .command_out(command_out),
        .control(control),
        .frequency_word(frequency_word),
        .amplitude_word(amplitude_word),
        .limits(limits),
        .status(status),
        .feature_version(feature_version),
        .clip_samples(clip_samples),
        .invalid_samples(invalid_samples),
        .fifo_rst_n(fifo_rst_n),
        .m_axis_tdata(m_axis_tdata),
        .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tlast(m_axis_tlast),
        .m_axis_tready(m_axis_tready)
    );
endmodule
