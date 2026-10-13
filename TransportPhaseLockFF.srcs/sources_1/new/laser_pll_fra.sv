`timescale 1ns / 1ps
// Closed-loop frequency response: inject d, observe e and u=e+d at the same edge.
// The existing HLS generator supplies lane 0; two existing demod_err IPs integrate
// synchronous sine/cosine products. Other probe lanes are zero. L=-E/U includes
// the complete physical return path and the active FPGA discriminator.
module laser_pll_fra #(parameter RAMP_INTERVAL_LOG2=6) (
    input wire clk, rst_n,
    input wire signed [15:0] error_code,
    input wire error_valid, error_saturated, dac_ready, phase_valid,
    // control[1] selects post-mixer/FIR I/Q observations; latched on arm.
    input wire signed [23:0] loopback_i, loopback_q,
    input wire loopback_valid, loopback_clipped,
    output wire [63:0] loopback_sum_i, loopback_sum_q,
    input wire [31:0] control, settle_clocks, measure_clocks,
    output wire [31:0] status,
    output reg [31:0] clip_samples, saturated_samples, outside_clip_samples, measured_samples,
    output wire [31:0] error_extrema, drive_extrema,
    output wire signed [15:0] drive_code,
    output wire drive_saturated,
    input wire [159:0] s_tone_tdata,
    input wire s_tone_tvalid,
    output wire s_tone_tready,
    input wire [271:0] s_ref_tdata,
    input wire s_ref_tvalid,
    output wire s_ref_tready,
    output wire [159:0] m_error_tdata, m_drive_tdata,
    output wire m_error_tvalid, m_drive_tvalid,
    input wire m_error_tready, m_drive_tready,
    output wire [271:0] m_error_ref_tdata, m_drive_ref_tdata,
    output wire m_error_ref_tvalid, m_drive_ref_tvalid,
    input wire m_error_ref_tready, m_drive_ref_tready
);
    localparam IDLE=0, RAMP_UP=1, SETTLE=2, MEASURE=3, RAMP_DOWN=4, DRAIN=5, DONE=6;
    reg [2:0] state;
    wire measuring = state==MEASURE;
    reg [31:0] remaining;
    reg [12:0] envelope; // 0..4096; one step / 64 clocks = 1.067 ms full ramp.
    reg [5:0] ramp_count;
    wire ramp_tick = ramp_count==((1<<RAMP_INTERVAL_LOG2)-1);
    reg [4:0] faults; // clipping, invalid phase, probe loss, generator gap, abort.
    reg signed [15:0] baseline;
    reg loopback_mode;
    // FIR samples have eight fractional bits. Keep two fractional bits in
    // the 20-bit HLS probes; six discarded bits are far below converter noise.
    wire signed [19:0] receive_i = loopback_i >>> 6;
    wire signed [19:0] receive_q = loopback_q >>> 6;
    wire probe_saturated = loopback_mode ? loopback_clipped : error_saturated;
    // 52 bits cover a signed 20-bit probe times any 32-bit window count.
    reg signed [51:0] sum_i, sum_q;
    assign loopback_sum_i={{12{sum_i[51]}},sum_i};
    assign loopback_sum_q={{12{sum_q[51]}},sum_q};
    always @(posedge clk) begin
        if (!rst_n || (state==IDLE && control[0])) begin sum_i<=0; sum_q<=0; end
        else if (measuring && loopback_mode) begin
            sum_i<=sum_i+receive_i; sum_q<=sum_q+receive_q;
        end
    end
    reg signed [15:0] error_min, error_max, drive_min, drive_max;
    wire busy = state!=IDLE && state!=DONE;
    wire paired = s_tone_tvalid && s_ref_tvalid;
    // Join by transaction number, so independent HLS output register slices
    // cannot pair a sine reference with the neighboring perturbation sample.
    assign s_tone_tready = s_ref_tvalid;
    assign s_ref_tready = s_tone_tvalid;

    reg signed [19:0] tone;
    reg signed [15:0] sine, cosine, sine_product, cosine_product, sine_injected, cosine_injected;
    (* use_dsp = "yes" *) reg signed [33:0] product;
    reg signed [20:0] injection;
    // This pipeline is only in the stimulus, never in the feedback signal.
    always @(posedge clk) begin
        if (!rst_n) begin
            tone<=0; sine<=0; cosine<=0; product<=0; injection<=0;
            sine_product<=0; cosine_product<=0; sine_injected<=0; cosine_injected<=0;
        end else begin
            if (paired) begin tone<=s_tone_tdata[19:0]; sine<=s_ref_tdata[15:0]; cosine<=s_ref_tdata[143:128]; end
            product<=tone*$signed({1'b0,envelope});
            injection<=product >>> 12;
            sine_product<=sine; cosine_product<=cosine;
            sine_injected<=sine_product; cosine_injected<=cosine_product;
        end
    end
    wire signed [21:0] sum = $signed(error_code) + $signed(injection);
    wire clipped = sum>32767 || sum < -32768;
    assign drive_code = sum>32767 ? 16'sh7fff : sum < -32768 ? 16'sh8000 : sum[15:0];
    assign drive_saturated = error_saturated || clipped;

    // Diagnose the actual integration window separately from turn-on/settling.
    // A bounded scope trace does not exclude an internal discriminator limiter.
    // Counters freeze at DONE and reset only at the next arm, not on host reads.
    always @(posedge clk) begin
        if (!rst_n || (state==IDLE && control[0])) begin
            clip_samples<=0; saturated_samples<=0; outside_clip_samples<=0; measured_samples<=0;
            error_min<=32767; error_max<=-32768; drive_min<=32767; drive_max<=-32768;
        end else if (measuring) begin
            measured_samples<=measured_samples+1'b1;
            if (clipped) clip_samples<=clip_samples+1'b1;
            if (probe_saturated) saturated_samples<=saturated_samples+1'b1;
            if (error_code<error_min) error_min<=error_code;
            if (error_code>error_max) error_max<=error_code;
            if (drive_code<drive_min) drive_min<=drive_code;
            if (drive_code>drive_max) drive_max<=drive_code;
        end else if (busy && (clipped || probe_saturated) && outside_clip_samples!=32'hffffffff)
            outside_clip_samples<=outside_clip_samples+1'b1;
    end
    assign error_extrema={error_max,error_min};
    assign drive_extrema={drive_max,drive_min};

    // Four independent AXIS handshakes share one record. A blocked reader never
    // stalls feedback: hold its data, drop new monitor records and flag the run.
    reg signed [19:0] error_probe, drive_probe;
    reg [271:0] reference;
    reg [3:0] pending;
    wire [3:0] ready = {m_drive_ref_tready,m_error_ref_tready,m_drive_tready,m_error_tready};
    wire room = !(|(pending & ~ready));
    always @(posedge clk) begin
        if (!rst_n) begin error_probe<=0; drive_probe<=0; reference<=0; pending<=0; end
        else if (room) begin
            error_probe <= loopback_mode ? receive_i : $signed(error_code)-$signed(baseline);
            drive_probe <= loopback_mode ? receive_q : $signed(drive_code)-$signed(baseline);
            reference <= {15'b0,measuring,112'b0,cosine_injected,112'b0,sine_injected};
            pending <= 4'b1111;
        end else pending <= pending & ~ready;
    end
    assign m_error_tdata={140'b0,error_probe};
    assign m_drive_tdata={140'b0,drive_probe};
    assign m_error_ref_tdata=reference;
    assign m_drive_ref_tdata=reference;
    assign {m_drive_ref_tvalid,m_error_ref_tvalid,m_drive_tvalid,m_error_tvalid}=pending;

    always @(posedge clk) begin
        if (!rst_n) begin state<=IDLE; remaining<=0; envelope<=0; ramp_count<=0; faults<=0; baseline<=0; loopback_mode<=0; end
        else begin
            if (busy) begin
                if (measuring && (clipped || probe_saturated)) faults[0]<=1;
                if (!(loopback_mode ? loopback_valid : phase_valid) || !error_valid || !dac_ready) faults[1]<=1;
                if (measuring && !room) faults[2]<=1;
                if (!paired) faults[3]<=1;
                if (!control[0] && state!=DRAIN) faults[4]<=1;
            end
            case (state)
                IDLE: begin
                    envelope<=0; ramp_count<=0;
                    if (control[0]) begin
                        faults<=0; baseline<=error_code; loopback_mode<=control[1]; state<=RAMP_UP;
                    end
                end
                RAMP_UP: begin
                    ramp_count<=ramp_tick ? 0 : ramp_count+1'b1;
                    if (ramp_tick) begin
                        envelope<=envelope+1'b1;
                        if (envelope==4095) begin state<=SETTLE; remaining<=settle_clocks; end
                    end
                end
                SETTLE: begin
                    if (remaining!=0) remaining<=remaining-1'b1;
                    else if (measure_clocks!=0) begin remaining<=measure_clocks; state<=MEASURE; end
                    else begin faults[4]<=1; state<=RAMP_DOWN; ramp_count<=0; end
                end
                MEASURE: begin
                    remaining<=remaining-1'b1;
                    if (remaining==1) begin state<=RAMP_DOWN; ramp_count<=0; end
                end
                RAMP_DOWN: begin
                    ramp_count<=ramp_tick ? 0 : ramp_count+1'b1;
                    if (envelope==0) begin remaining<=16; state<=DRAIN; end
                    else if (ramp_tick) envelope<=envelope-1'b1;
                end
                DRAIN: begin
                    remaining<=remaining-1'b1;
                    if (remaining==1) state<=DONE;
                end
                DONE: if (!control[0]) state<=IDLE;
                default: state<=IDLE;
            endcase
            // Operator abort ramps the stimulus down; it does not reset the PLL.
            if (!control[0] && state>=RAMP_UP && state<=MEASURE) begin
                state<=RAMP_DOWN; ramp_count<=0;
            end
        end
    end
    assign status={envelope,11'b0,faults,state==DONE,measuring,busy};
endmodule
