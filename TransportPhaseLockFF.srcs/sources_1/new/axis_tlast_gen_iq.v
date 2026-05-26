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
    wire handshake;
    
    initial begin
        counter = 0;
    end
        
    assign handshake = (s_axis_1_tvalid & s_axis_2_tvalid) & m_axis_tready;
    
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
            if (handshake) begin
                if (m_axis_tlast) begin
                    counter <= 1'b1;
                end else begin
                    counter <= counter + 1'b1;
                end
            end
        end
    end
    
    assign m_axis_tdata = {s_axis_1_tdata, s_axis_2_tdata};
    assign m_axis_tvalid = s_axis_1_tvalid & s_axis_2_tvalid;
    assign s_axis_1_tready = m_axis_tready;
    assign s_axis_2_tready = m_axis_tready;
    
    assign m_axis_tlast = (counter == pkt_length_reg) & handshake;
    
endmodule

