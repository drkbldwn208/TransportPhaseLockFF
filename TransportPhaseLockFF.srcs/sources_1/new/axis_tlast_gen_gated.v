`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/06/2026 11:34:02 AM
// Design Name: 
// Module Name: axis_tlast_gen
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


module axis_tlast_gen_gated(
    input wire aclk,
    input wire aresetn,
    
    input wire [31:0] pkt_length_cycles,
    
    input wire start,
    
    input wire [127:0] s_axis_tdata,
    input wire s_axis_tvalid,
    output wire s_axis_tready,
    
    output reg [127:0] m_axis_tdata,
    output reg m_axis_tvalid,
    input wire m_axis_tready,
    output reg m_axis_tlast,
    
    output reg overflow,
    output reg done
    );
    
    assign s_axis_tready = 1'b1;
    
    reg [31:0] counter;
    reg [31:0] pkt_length_reg;
    
    (* ASYNC_REG = "TRUE" *) reg [2:0] start_sync;
    wire start_pulse;
    
    assign start_pulse = start_sync[1] && !start_sync[2];
    
    localparam IDLE = 1'b0;
    localparam ACQ = 1'b1;
    reg st;
    
    always @(posedge aclk) begin
        if (!aresetn) begin
            pkt_length_reg <= 32'd1024;
            st <= IDLE;
            counter <= 32'd1;
            start_sync <= 3'b0;
            m_axis_tvalid <= 1'b0;
            m_axis_tlast <= 1'b0;
            m_axis_tdata <= 128'b0;
            overflow <= 1'b0;
            done <= 1'b0;
        end else begin
            start_sync <= {start_sync[1:0], start};
            pkt_length_reg <= pkt_length_cycles;
            done <= 1'b0;
            if (m_axis_tvalid && m_axis_tready) begin
                m_axis_tvalid <= 1'b0;
                if (m_axis_tlast) done <= 1'b1;
                m_axis_tlast <= 1'b0;
            end
        
        case (st)
            IDLE: 
                if (start_pulse) begin
                    st <= ACQ;
                    counter <= 32'd1;
                end
            
            ACQ: 
                if (s_axis_tvalid) begin
                    if (m_axis_tvalid && !m_axis_tready) begin
                        //downstream stalled path
                        overflow <= 1'b1;
                    end else begin
                        m_axis_tdata <= s_axis_tdata;
                        m_axis_tvalid <= 1'b1;
                        m_axis_tlast <= (counter == pkt_length_reg);
                        
                        if (counter == pkt_length_reg) begin
                            st <= IDLE;
                            counter <= 32'd1;
                        end else begin
                            counter <= counter + 32'd1;
                        end
                    end
                end
            endcase
        end
    end
    
endmodule

