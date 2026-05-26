`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/03/2026 01:30:22 PM
// Design Name: 
// Module Name: PhaseExtractor
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


module PhaseExtractor #(
  parameter int DATA_WIDTH = 16,
  parameter int PHASE_WIDTH = 12,
  parameter int AXIS_WIDTH = 8,
  parameter int BUS_WIDTH = 128
)(
  input logic clk,
  input logic rst_n,
  input logic signed [BUS_WIDTH-1:0] I_tdata,
  input logic                        I_tvalid,
  input logic signed [BUS_WIDTH-1:0] Q_tdata,
  input logic                        Q_tvalid,

  output logic signed [(PHASE_WIDTH*8)-1:0] phase_error_out

);

  //Unpack input data from 128-bit buses to 16-bit x 8 buses for both I and Q, and pass tvalid for each
  logic signed [DATA_WIDTH-1:0] I_tdata_reg [7:0];
  logic signed [DATA_WIDTH-1:0] Q_tdata_reg [7:0];
  logic I_tvalid_reg [7:0];
  logic Q_tvalid_reg [7:0];
  
  
  
  always_ff @(posedge clk) begin
    if(!rst_n) begin
      for(int i = 0; i < 8; i++) begin
        I_tdata_reg[i] <= '0;
        Q_tdata_reg[i] <= '0;
        I_tvalid_reg[i] <= '0;
        Q_tvalid_reg[i] <= '0;
      end
    end else begin
      for(int i = 0; i < 8; i++) begin
        I_tdata_reg[i] <= I_tdata[i*DATA_WIDTH +: DATA_WIDTH];
        Q_tdata_reg[i] <= Q_tdata[i*DATA_WIDTH +: DATA_WIDTH];
        I_tvalid_reg[i] <= I_tvalid;
        Q_tvalid_reg[i] <= Q_tvalid;
      end
    end
  end


  logic signed [(2*DATA_WIDTH)-1:0] arctan_tdata_in [7:0];
  logic arctan_tvalid_in [7:0];
  genvar i;
  generate
    for(i = 0; i < 8; i++) begin
    
        
      assign arctan_tdata_in[i] = {Q_tdata_reg[i], I_tdata_reg[i]};
      assign arctan_tvalid_in[i] = I_tvalid_reg[i] && Q_tvalid_reg[i];
        
      wire [PHASE_WIDTH-1:0] cordic_phase_out;
      cordic_arctan u_arctan (
        .aclk(clk),
        .s_axis_cartesian_tdata(arctan_tdata_in[i]),
        .s_axis_cartesian_tvalid(arctan_tvalid_in[i]),
        .m_axis_dout_tdata(cordic_phase_out),
        .m_axis_dout_tvalid()
      );
      
      assign phase_error_out[i*PHASE_WIDTH +: PHASE_WIDTH] = cordic_phase_out;
    end
  endgenerate
endmodule
