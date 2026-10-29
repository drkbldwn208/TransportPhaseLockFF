`timescale 1ns / 1ps
// Shot monitor only: no backpressure or added registers in the servo path.
// Record words, lowest first: error Q17.8 signed32; {measured,reference} u16;
// {raw_adc signed16,actuator u16}; {reserved16,flags16}.
// Keep one unissued frame so the last uniformly spaced sample can receive TLAST
// when the streamer stops, even when the stop falls between sample strobes.
module intensity_shot_capture (
    input wire clk, rst_n, shot_active, sample_valid,
    input wire signed [31:0] error_q8,
    input wire [15:0] reference_power, measured_power, actuator_codes,
    input wire signed [15:0] raw_adc,
    input wire [15:0] sample_flags,
    input wire [31:0] control, tail_clocks,
    output wire [31:0] status, feature_version,
    output wire fifo_rst_n,
    output reg [127:0] m_axis_tdata,
    output reg m_axis_tvalid, m_axis_tlast,
    input wire m_axis_tready
);
    localparam WAIT=2'd0, RUN=2'd1, FINISH=2'd2, DONE=2'd3;
    reg [1:0] state;
    reg initialized, active_d, tail_running;
    reg overflow_seen, truncated_seen, invalid_seen, changed_seen;
    reg [31:0] saved_control, saved_tail, remaining_tail;
    reg [23:0] count, maximum_frames;
    reg [31:0] interval_count, interval_mask;
    reg [127:0] pending_data;
    reg [15:0] flags_since_sample;
    reg pending_valid;
    wire armed=control[0];
    wire start_edge=shot_active && !active_d;
    wire stop_edge=!shot_active && active_d;
    wire output_free=!m_axis_tvalid || m_axis_tready;
    wire finish_now=(stop_edge && saved_tail==0) ||
                    (tail_running && remaining_tail<=1);
    wire [127:0] frame={16'd0,(sample_flags | flags_since_sample),raw_adc,actuator_codes,
                         measured_power,reference_power,error_q8};
    assign fifo_rst_n=rst_n && armed;
    assign feature_version=32'h49533031; // IS01; independent of legacy FRA ABI
    // Low status bits: waiting,running,done,overflow,truncated,invalid,changed,0.
    assign status={count,1'b0,changed_seen,invalid_seen,truncated_seen,
                   overflow_seen,(state==DONE),(state==RUN),
                   (armed && initialized && state==WAIT)};

    always @(posedge clk) begin
        if (!rst_n) active_d<=0;
        else active_d<=shot_active;
        if (!rst_n || !armed) begin
            state<=WAIT; initialized<=0; tail_running<=0; remaining_tail<=0;
            overflow_seen<=0; truncated_seen<=0; invalid_seen<=0; changed_seen<=0;
            saved_control<=0; saved_tail<=0; count<=0; maximum_frames<=0;
            interval_count<=0; interval_mask<=0;
            pending_data<=0; pending_valid<=0;
            flags_since_sample<=0;
            m_axis_tdata<=0; m_axis_tvalid<=0; m_axis_tlast<=0;
        end else begin
            if (m_axis_tvalid && m_axis_tready) begin
                m_axis_tvalid<=0;
                if (m_axis_tlast) state<=DONE;
            end
            if (!initialized) begin
                initialized<=1;
                saved_control<=control; saved_tail<=tail_clocks;
                maximum_frames<=control[31:8]==0 ? 24'd1 : control[31:8];
                // Software limits D to 3..24; hardware also prevents wrap.
                interval_mask<=(32'd1 << (control[5:1]>24 ? 5'd24 : control[5:1]))-1'b1;
            end else begin
                if (control!=saved_control || tail_clocks!=saved_tail) changed_seen<=1;
                if (state==WAIT && start_edge) begin
                    state<=RUN; pending_data<=frame; pending_valid<=1; count<=1;
                    interval_count<=0;
                    flags_since_sample<=0;
                    if (!sample_valid) invalid_seen<=1;
                    if (maximum_frames==1) begin state<=FINISH; truncated_seen<=1; end
                end
                if (state==RUN) begin
                    flags_since_sample<=flags_since_sample | sample_flags;
                    if (!sample_valid) invalid_seen<=1;
                    if (stop_edge && saved_tail!=0) begin
                        tail_running<=1; remaining_tail<=saved_tail;
                    end else if (tail_running && remaining_tail!=0)
                        remaining_tail<=remaining_tail-1'b1;
                    if (finish_now) state<=FINISH;
                    else if (interval_count==interval_mask) begin
                        interval_count<=0;
                        if (output_free) begin
                            m_axis_tdata<=pending_data;
                            m_axis_tvalid<=pending_valid; m_axis_tlast<=0;
                            pending_data<=frame; pending_valid<=1;
                            flags_since_sample<=0;
                            count<=count+1'b1;
                            if (count==maximum_frames-1'b1) begin
                                state<=FINISH; truncated_seen<=1;
                            end
                        end else overflow_seen<=1;
                    end else interval_count<=interval_count+1'b1;
                end
                if (state==FINISH && pending_valid && output_free) begin
                    m_axis_tdata<={pending_data[127:112],
                                  (pending_data[111:96] | flags_since_sample),pending_data[95:0]};
                    m_axis_tvalid<=1; m_axis_tlast<=1;
                    pending_valid<=0;
                end
            end
        end
    end
endmodule
