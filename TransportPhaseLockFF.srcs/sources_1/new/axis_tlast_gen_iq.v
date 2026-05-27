`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 05/26/2026 11:47:18 AM
// Design Name: 
// Module Name: axis_tlast_gen_iq
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


module axis_tlast_gen_iq(
    input wire aclk,
    input wire aresetn,
    
    input wire [31:0] pkt_length_cycles,
    
    
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_1 TDATA" *) 
    input wire [63:0] s_axis_1_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_1 TVALID" *)
    input wire s_axis_1_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_1 TREADY" *)
    output wire s_axis_1_tready,
    
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_2 TDATA" *) 
    input wire [63:0] s_axis_2_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_2 TVALID" *)
    input wire s_axis_2_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis_2 TREADY" *)
    output wire s_axis_2_tready,
    
    
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TDATA" *)
    output wire [127:0] m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TVALID" *)
    output wire m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TREADY" *)
    input wire m_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TLAST" *)
    output wire m_axis_tlast
    );
    
    reg [31:0] counter;
    reg [31:0] pkt_length_reg;
    wire inputs_valid;
    wire output_fire;
    wire [31:0] last_count;
    wire packet_last;
    
    initial begin
        counter = 0;
    end
        
    // Pack one beat only when both I and Q words are present.  The ready
    // signals are cross-gated so one side cannot be consumed by itself.
    assign inputs_valid = s_axis_1_tvalid & s_axis_2_tvalid;
    assign output_fire = inputs_valid & m_axis_tready;
    
    always @(posedge aclk) begin
        if (!aresetn) begin
            pkt_length_reg <= 32'd1024;
        end else begin
            pkt_length_reg <= pkt_length_cycles;
        end
    end
    
    always @(posedge aclk) begin
        if (!aresetn) begin
            counter <= 0;
        end else begin
            if (output_fire) begin
                if (packet_last) begin
                    counter <= 32'd0;
                end else begin
                    counter <= counter + 1'b1;
                end
            end
        end
    end
    
    // s_axis_1 occupies the upper 64 bits and s_axis_2 occupies the lower
    // 64 bits.  Software reading int64[2] from little-endian memory will see
    // s_axis_2 first and s_axis_1 second.
    assign m_axis_tdata = {s_axis_1_tdata, s_axis_2_tdata};
    assign m_axis_tvalid = inputs_valid;
    assign s_axis_1_tready = m_axis_tready & s_axis_2_tvalid;
    assign s_axis_2_tready = m_axis_tready & s_axis_1_tvalid;
    
    // pkt_length_cycles is the packet length in 128-bit output beats.
    // A zero length is treated as one beat to keep TLAST well-defined.
    assign last_count = (pkt_length_reg == 32'd0) ? 32'd0 : (pkt_length_reg - 32'd1);
    assign packet_last = (counter == last_count);
    assign m_axis_tlast = m_axis_tvalid & packet_last;
    
endmodule
