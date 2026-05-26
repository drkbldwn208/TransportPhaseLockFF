`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/03/2026 01:59:36 PM
// Design Name: 
// Module Name: PhaseExtractor_Wrapper
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


module PhaseExtractor_Wrapper (
  input clk,
  input rst_n,
  input [127:0] I_tdata,
  input I_tvalid,
  output I_tready,
  input [127:0] Q_tdata,
  input Q_tvalid,
  output Q_tready,
  output[95:0] phase_error_out,
  output tvalid_passthrough,
  input tready_passthrough
);

  PhaseExtractor #(
  .DATA_WIDTH(16),
  .PHASE_WIDTH(12)
  ) PhaseExtractorInst (
  .clk(clk),
  .rst_n(rst_n),
  .I_tdata(I_tdata),
  .I_tvalid(I_tvalid),
  .Q_tdata(Q_tdata),
  .Q_tvalid(Q_tvalid),
  .phase_error_out(phase_error_out)
  );
  
  assign tvalid_passthrough = I_tvalid & Q_tvalid;
  assign I_tready = tready_passthrough;
  assign Q_tready = tready_passthrough;
endmodule
