`timescale 1ns / 1ps
module intensity_shot_capture_wrapper (
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF m_axis, ASSOCIATED_RESET rst_n:fifo_rst_n" *)
    input wire clk,
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *) input wire rst_n,
    input wire shot_active, sample_valid,
    input wire signed [31:0] error_q8,
    input wire [15:0] reference_power, measured_power, actuator_codes,
    input wire signed [15:0] raw_adc,
    input wire [15:0] sample_flags,
    input wire [31:0] control, tail_clocks,
    output wire [31:0] status, feature_version,
    output wire fifo_rst_n,
    output wire [127:0] m_axis_tdata,
    output wire m_axis_tvalid, m_axis_tlast,
    input wire m_axis_tready
);
    intensity_shot_capture capture (
        .clk(clk),.rst_n(rst_n),.shot_active(shot_active),.sample_valid(sample_valid),
        .error_q8(error_q8),.reference_power(reference_power),.measured_power(measured_power),
        .actuator_codes(actuator_codes),.raw_adc(raw_adc),.sample_flags(sample_flags),
        .control(control),.tail_clocks(tail_clocks),.status(status),.feature_version(feature_version),
        .fifo_rst_n(fifo_rst_n),.m_axis_tdata(m_axis_tdata),.m_axis_tvalid(m_axis_tvalid),
        .m_axis_tlast(m_axis_tlast),.m_axis_tready(m_axis_tready)
    );
endmodule
