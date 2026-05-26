`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/04/2026 09:43:42 AM
// Design Name: 
// Module Name: NCO
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


module NCO #(
    parameter int PHASE_WIDTH = 32,
    parameter int ADDR_WIDTH = 14,
    parameter int AMP_WIDTH = 16,
    parameter int OUT_WIDTH = 16
    )(
    input logic clk,
    input logic rst_n,
    
    input logic signed [8*PHASE_WIDTH - 1:0] phase_in,
    
    output logic signed [8*OUT_WIDTH - 1:0] nco_out
    );
    
    logic [1:0] quadrant [7:0];
    logic [ADDR_WIDTH - 1:0] addr [7:0];
    logic [ADDR_WIDTH - 1:0] lut_addr [7:0];
    logic [AMP_WIDTH - 1:0] lut_data [7:0];
    
    genvar i;
    generate
        for(i = 0;i < 8;i++) begin
            assign quadrant[i] = phase_in[(i+1)*PHASE_WIDTH - 1 -: 2];
            assign addr[i] = phase_in[(i+1)*PHASE_WIDTH - 3 -: ADDR_WIDTH];
            assign lut_addr[i] = (quadrant[i][0]) ? ((1 << ADDR_WIDTH) - 1 - addr[i]) : addr[i];
        end
    endgenerate
    
    
    //Four dual-port BRAMs for 8 reads per clock
  reg [AMP_WIDTH-1:0] sine_lut_1 [0:(1<<ADDR_WIDTH)-1];
  reg [AMP_WIDTH-1:0] sine_lut_2 [0:(1<<ADDR_WIDTH)-1];
  reg [AMP_WIDTH-1:0] sine_lut_3 [0:(1<<ADDR_WIDTH)-1];
  reg [AMP_WIDTH-1:0] sine_lut_4 [0:(1<<ADDR_WIDTH)-1];
  initial begin
    $readmemh("/home/levlabcukomen/Desktop/PythonScripts/sine_lut.hex", sine_lut_1);
    $readmemh("/home/levlabcukomen/Desktop/PythonScripts/sine_lut.hex", sine_lut_2);
    $readmemh("/home/levlabcukomen/Desktop/PythonScripts/sine_lut.hex", sine_lut_3);
    $readmemh("/home/levlabcukomen/Desktop/PythonScripts/sine_lut.hex", sine_lut_4);
    if (sine_lut_1[0] === 1'bx) $display("WARNING: sine_lut_1[0] is X - readmemh failed or file missing");
    else $display("sine LUT loaded OK, sample[0]=%h", sine_lut_1[0]);
  end
  
  //Read LUT
  always_ff @(posedge clk) begin
    lut_data[0] <= sine_lut_1[lut_addr[0]];
    lut_data[1] <= sine_lut_1[lut_addr[1]];
    lut_data[2] <= sine_lut_2[lut_addr[2]];
    lut_data[3] <= sine_lut_2[lut_addr[3]];
    lut_data[4] <= sine_lut_3[lut_addr[4]];
    lut_data[5] <= sine_lut_3[lut_addr[5]];
    lut_data[6] <= sine_lut_4[lut_addr[6]];
    lut_data[7] <= sine_lut_4[lut_addr[7]];
  end
  
  logic [1:0] quadrant_reg [7:0];
  
  genvar j;
  generate
    for (j = 0; j < 8; j++) begin    
        logic signed [AMP_WIDTH:0] signed_val;
        logic signed [AMP_WIDTH:0] rounded_val;
        
        logic [1:0] current_quadrant;
        
        assign current_quadrant = quadrant_reg[j];
        
        logic [AMP_WIDTH-1:0] current_lut_data;
        
        assign current_lut_data = lut_data[j];
        
        assign signed_val = current_quadrant[1] ? -$signed({1'b0, current_lut_data}) : $signed({1'b0, current_lut_data});
        
        assign rounded_val = signed_val + (1 << (AMP_WIDTH - OUT_WIDTH + 1)); 
    
        always_ff @(posedge clk) begin
            if (!rst_n) begin
                quadrant_reg[j] <= 2'b0;
                nco_out[j*OUT_WIDTH +: OUT_WIDTH] <= 0;
            end else begin
                quadrant_reg[j] <= quadrant[j];
                nco_out[j*OUT_WIDTH +: OUT_WIDTH] <= $signed(rounded_val) >>> (AMP_WIDTH - OUT_WIDTH + 1);
            end
        end
    end
  endgenerate
  

          
endmodule

