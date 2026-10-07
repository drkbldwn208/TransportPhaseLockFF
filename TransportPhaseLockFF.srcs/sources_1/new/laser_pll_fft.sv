`timescale 1ns / 1ps
// Occasional 1024-sample raw-ADC spectra. This is NOT in the fast phase path.
// Fs=1966.08 MHz, bin spacing=1.92 MHz, snapshot duration=0.520833 us.
module laser_pll_fft (
    input wire clk,
    input wire rst_n,
    input wire [127:0] adc_data,
    input wire adc_valid,
    input wire [15:0] minimum_peak,
    output reg [9:0] peak_bin,
    output reg estimate_valid,
    output wire [31:0] fft_status
);
    localparam CAPTURE=0, CONFIGURE=1, READ_SAMPLE=2, WINDOW=3,
               SEND_SAMPLE=4, WAIT_RESULT=5, PUBLISH=6;
    reg [2:0] state;
    // Wide writes capture all eight chronological samples without ADC stalls.
    (* ram_style="block" *) reg [127:0] snapshot [0:127];
    (* rom_style="block" *) reg [15:0] hann [0:1023];
    initial $readmemh("laser_pll_hann.mem", hann);
    reg [6:0] write_address;
    reg [9:0] sample_index;
    reg [127:0] sample_word;
    reg [15:0] window_coefficient;
    reg signed [32:0] window_product;
    wire signed [15:0] sample_value = sample_word[16*sample_index[2:0] +: 16];
    always @(posedge clk) begin
        if (state==CAPTURE && adc_valid) snapshot[write_address] <= adc_data;
        if (state==READ_SAMPLE) begin
            sample_word <= snapshot[sample_index[9:3]];
            window_coefficient <= hann[sample_index];
        end
        if (state==WINDOW)
            window_product <= sample_value * $signed({1'b0,window_coefficient});
    end

    wire config_ready, input_ready, fft_valid, fft_last;
    wire [31:0] fft_data;
    wire [23:0] fft_user;
    wire overflow_event, unexpected_last, missing_last;
    // FWD_INV=1 in bit 0; SCALE_SCH=0x55556 occupies bits 20:1.
    // AMD's conservative radix-2 schedule: /4 first stage, /2 next nine.
    // Hann-windowed, bin-centred real tone: FFT peak ~= ADC peak / 8.
    laser_pll_fft_core fft_core (
        .aclk(clk), .aresetn(rst_n),
        .s_axis_config_tdata(24'h0aaaad),
        .s_axis_config_tvalid(state==CONFIGURE), .s_axis_config_tready(config_ready),
        .s_axis_data_tdata({16'b0,window_product[30:15]}),
        .s_axis_data_tvalid(state==SEND_SAMPLE), .s_axis_data_tready(input_ready),
        .s_axis_data_tlast(sample_index==1023),
        .m_axis_data_tdata(fft_data), .m_axis_data_tuser(fft_user),
        .m_axis_data_tvalid(fft_valid), .m_axis_data_tready(1'b1),
        .m_axis_data_tlast(fft_last),
        .m_axis_status_tdata(), .m_axis_status_tvalid(), .m_axis_status_tready(1'b1),
        .event_frame_started(), .event_tlast_unexpected(unexpected_last),
        .event_tlast_missing(missing_last), .event_fft_overflow(overflow_event),
        .event_status_channel_halt(), .event_data_in_channel_halt(),
        .event_data_out_channel_halt()
    );
    // Bit-reversed output saves reordering storage; XK_INDEX names each bin.
    wire signed [15:0] real_part = fft_data[15:0];
    wire signed [15:0] imag_part = fft_data[31:16];
    reg [31:0] real_squared, imag_squared;
    reg [32:0] power;
    reg [9:0] bin1, bin2;
    reg valid1, valid2, last1, last2;
    always @(posedge clk) begin
        real_squared <= real_part * real_part;
        imag_squared <= imag_part * imag_part;
        power <= {1'b0,real_squared} + {1'b0,imag_squared};
        bin1 <= fft_user[9:0]; bin2 <= bin1;
        valid1 <= rst_n && fft_valid; valid2 <= rst_n && valid1;
        last1 <= fft_last; last2 <= last1;
    end
    // Search 199.68..950.40 MHz, including the bin nearest 200 MHz.
    wire in_band = bin2>=104 && bin2<=495;
    reg [32:0] peak_power;
    reg [41:0] band_power;
    reg [9:0] candidate_bin;
    reg frame_fault, overflow_seen, protocol_fault, weak_signal;
    reg [7:0] frame_number;
    reg [19:0] age;
    reg [31:0] threshold_power;
    always @(posedge clk) threshold_power <= minimum_peak * minimum_peak;
    // A dominant tone must contribute >=1/8 of the in-band spectral energy
    // in its strongest bin. This rejects broadband noise, not competing tones.
    wire dominant_peak = peak_power >= {1'b0,threshold_power} && peak_power!=0 &&
                  ({9'b0,peak_power} << 3) >= band_power;
    always @(posedge clk) begin
        if (!rst_n) begin
            state <= CAPTURE; write_address <= 0; sample_index <= 0;
            peak_bin <= 0; estimate_valid <= 0; peak_power <= 0;
            band_power <= 0; candidate_bin <= 0; frame_fault <= 0;
            overflow_seen <= 0; protocol_fault <= 0; weak_signal <= 0;
            frame_number <= 0; age <= 0;
        end else begin
            if (age != 20'hfffff) age <= age+1'b1;
            // Missing raw data or a hung transform invalidates a held estimate.
            if (!adc_valid || age==20'hfffff) estimate_valid <= 0;
            if (!adc_valid && state!=CAPTURE) frame_fault <= 1;
            if (overflow_event || unexpected_last || missing_last) frame_fault <= 1;
            if (overflow_event) overflow_seen <= 1;
            if (unexpected_last || missing_last) protocol_fault <= 1;
            case (state)
                CAPTURE: begin
                    if (!adc_valid) write_address <= 0;
                    else if (write_address==127) begin
                        state <= CONFIGURE; write_address <= 0;
                        sample_index <= 0; peak_power <= 0; band_power <= 0;
                        candidate_bin <= 0; frame_fault <= 0;
                    end else write_address <= write_address+1'b1;
                end
                CONFIGURE: if (config_ready) state <= READ_SAMPLE;
                READ_SAMPLE: state <= WINDOW;
                WINDOW: state <= SEND_SAMPLE;
                SEND_SAMPLE: if (input_ready) begin
                    if (sample_index==1023) state <= WAIT_RESULT;
                    else begin sample_index <= sample_index+1'b1; state <= READ_SAMPLE; end
                end
                WAIT_RESULT: if (valid2 && last2) state <= PUBLISH;
                PUBLISH: begin
                    peak_bin <= candidate_bin;
                    estimate_valid <= dominant_peak && !frame_fault && adc_valid;
                    weak_signal <= !dominant_peak;
                    frame_number <= frame_number+1'b1;
                    age <= 0; state <= CAPTURE;
                end
                default: state <= CAPTURE;
            endcase
            if (valid2 && in_band) begin
                band_power <= band_power+power;
                if (power>peak_power) begin peak_power <= power; candidate_bin <= bin2; end
            end
        end
    end
    // Bits 31:24 identify this register layout; sticky faults clear on reset.
    assign fft_status = {8'hA3,frame_number,2'b0,protocol_fault,overflow_seen,
                         weak_signal,estimate_valid,peak_bin};
endmodule
