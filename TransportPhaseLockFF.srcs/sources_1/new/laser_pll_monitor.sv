`timescale 1ns / 1ps
// Independent finite I/Q capture; no backpressure can reach the laser loop.
// Boxcar mean of 2^D post-DDC samples, retaining their 8 fractional ADC bits.
// GPIO: [0] arm, [5:1] D (0..16), [31:12] output sample count (1..1048575).
// Packed {I64,Q64}, as in the former axi_dma_3 path. Invalid input is included
// as zero and flagged, keeping the sample time grid rather than hiding gaps.
module laser_pll_monitor (
    input wire clk,
    input wire rst_n,
    input wire signed [23:0] i_sample,
    input wire signed [23:0] q_sample,
    input wire sample_valid,
    input wire [31:0] monitor_control,
    output wire [31:0] monitor_status,
    output wire fifo_rst_n,
    output reg [127:0] m_axis_tdata,
    output reg m_axis_tvalid,
    input wire m_axis_tready,
    output reg m_axis_tlast
);
    wire enabled=monitor_control[0];
    reg started, collecting, done, overflow_seen, invalid_seen;
    reg [4:0] decimation_log2;
    reg [19:0] sample_limit, samples_queued;
    reg [15:0] window_count;
    reg signed [40:0] sum_i, sum_q;
    wire [15:0] window_mask=(17'd1 << decimation_log2)-1'b1;
    wire signed [40:0] next_i=sum_i+(sample_valid ? $signed(i_sample) : 24'sd0);
    wire signed [40:0] next_q=sum_q+(sample_valid ? $signed(q_sample) : 24'sd0);
    wire signed [40:0] mean_i=next_i >>> decimation_log2;
    wire signed [40:0] mean_q=next_q >>> decimation_log2;
    assign fifo_rst_n=rst_n && enabled;
    assign monitor_status={samples_queued,8'b0,invalid_seen,overflow_seen,done,collecting};
    always @(posedge clk) begin
        if (!rst_n || !enabled) begin
            started<=0; collecting<=0; done<=0; overflow_seen<=0; invalid_seen<=0;
            decimation_log2<=0; sample_limit<=0; samples_queued<=0;
            window_count<=0; sum_i<=0; sum_q<=0;
            m_axis_tdata<=0; m_axis_tvalid<=0; m_axis_tlast<=0;
        end else begin
            if (!started) begin
                started<=1; collecting<=monitor_control[31:12]!=0;
                sample_limit<=monitor_control[31:12];
                decimation_log2<=monitor_control[5:1]>16 ? 5'd16 : monitor_control[5:1];
            end
            if (m_axis_tvalid && m_axis_tready) begin
                m_axis_tvalid<=0;
                if (m_axis_tlast) done<=1;
            end
            if (collecting) begin
                if (!sample_valid) invalid_seen<=1;
                if (window_count==window_mask) begin
                    window_count<=0; sum_i<=0; sum_q<=0;
                    if (!m_axis_tvalid || m_axis_tready) begin
                        m_axis_tdata<={{23{mean_i[40]}},mean_i,{23{mean_q[40]}},mean_q};
                        m_axis_tvalid<=1;
                        m_axis_tlast<=samples_queued==sample_limit-1'b1;
                        samples_queued<=samples_queued+1'b1;
                        if (samples_queued==sample_limit-1'b1) collecting<=0;
                    end else overflow_seen<=1;
                end else begin
                    window_count<=window_count+1'b1;
                    sum_i<=next_i; sum_q<=next_q;
                end
            end
        end
    end
endmodule
