`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 05/26/2026 02:31:00 PM
// Design Name: 
// Module Name: axis_round_saturate
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


module axis_round_saturate #(
    parameter integer IN_WIDTH = 32,
    parameter integer OUT_WIDTH = 18,
    parameter integer DROP_LSBS = 0,
    parameter integer BUS_WIDTH = 24
    )(
    input wire clk,
    input wire rst_n,
    
    input wire s_axis_tvalid, 
    output wire s_axis_tready,
    input wire signed [IN_WIDTH-1:0] s_axis_tdata,
    
    output wire m_axis_tvalid,
    input wire m_axis_tready,
    output wire signed [BUS_WIDTH-1:0] m_axis_tdata
    );
    
    assign s_axis_tready = m_axis_tready;
    assign m_axis_tvalid = rst_n && s_axis_tvalid;
    
    wire signed [IN_WIDTH-1:0] rounded_data;
    
    generate 
        if (DROP_LSBS > 0) begin: gen_rounding
            assign rounded_data = s_axis_tdata + (1 << (DROP_LSBS - 1));
        end else begin : gen_no_rounding
            assign rounded_data = s_axis_tdata;
        end
    endgenerate
    
    localparam integer KEEP_BITS = OUT_WIDTH + DROP_LSBS;
    
    reg signed [OUT_WIDTH-1:0] next_tdata;
    
    always @* begin
        if (KEEP_BITS >= IN_WIDTH) begin
            next_tdata = rounded_data[IN_WIDTH-1 : DROP_LSBS];
        end else begin
            if (rounded_data[IN_WIDTH-1] == 1'b0 && |rounded_data[IN_WIDTH-2 : KEEP_BITS-1]) begin
                next_tdata = {1'b0, {(OUT_WIDTH-1){1'b1}}};
            end else if (rounded_data[IN_WIDTH-1] == 1'b1 && ~&rounded_data[IN_WIDTH-2 : KEEP_BITS-1]) begin
                next_tdata = {1'b1, {(OUT_WIDTH-1){1'b0}}};
            end else begin
                next_tdata = rounded_data[KEEP_BITS-1 : DROP_LSBS];
            end
        end
    end 
    
    assign m_axis_tdata =
        rst_n ? {{(BUS_WIDTH - OUT_WIDTH){next_tdata[OUT_WIDTH-1]}}, next_tdata}
              : {BUS_WIDTH{1'b0}};
        
endmodule
