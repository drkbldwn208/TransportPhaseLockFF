`timescale 1ns / 1ps
// Calibrated intensity control. Optical power uses 16 unsigned codes over one
// common physical scale, independent of PD attenuation. Runtime lookup tables
// replace nonlinear arithmetic. Reset selects the original HLS controller.
module intensity_linearized (
    input wire clk, rst_n, adc_valid, shot_active,
    input wire [63:0] adc_bus,
    input wire [15:0] reference_in, legacy_command,
    input wire [31:0] control, write_address, write_data,
    output wire [31:0] status, read_data, feature_version,
    output wire [15:0] command_out, reference_power, measured_power,
    output wire signed [31:0] error_q8,
    output wire signed [15:0] raw_adc,
    output wire [15:0] sample_flags
);
    wire requested=control[0];
    wire high_mode=control[3];
    wire [17:0] address=write_address[17:0];
    reg write_toggle, config_fault;
    reg [31:0] epoch;
    wire write_event=write_address[31]!=write_toggle;
    wire accept_write=rst_n && write_event && !requested && !shot_active;
    reg [14:0] low_count, high_count;
    reg [16:0] output_count;
    wire low_loaded=low_count==16384;
    wire high_loaded=high_count==16384;
    wire output_loaded=output_count==65536;
    wire ready=(high_mode ? high_loaded : low_loaded) && output_loaded;
    wire active=requested && ready;
    reg [31:0] previous_control;
    // Cover the longest (shelf-enabled) pipeline after enabling or invalid data.
    reg [12:0] valid_history;
    wire control_changed=control!=previous_control;
    always @(posedge clk) begin
        previous_control<=control;
        if (!rst_n || !active || control_changed || !adc_valid) valid_history<=0;
        else valid_history<={valid_history[11:0],1'b1};
    end
    reg signed [17:0] kp;
    reg [19:0] alpha1,alpha2,alpha3;
    reg [31:0] lead_alpha;
    reg signed [17:0] lead_gain;
    reg [23:0] inverse_power_scale;
    reg [31:0] low_limits,high_limits;
    reg [15:0] maximum_fraction,maximum_command;
    // One write port and one registered read port per block RAM. No reset of
    // RAM contents: full sequential loads are required before activation.
    (* ram_style="block" *) reg [15:0] sensor_low [0:16383];
    (* ram_style="block" *) reg [15:0] sensor_high [0:16383];
    (* ram_style="block" *) reg [15:0] actuator_inverse [0:65535];
    always @(posedge clk) begin
        if (accept_write && address<18'h04000) sensor_low[address[13:0]]<=write_data[15:0];
        if (accept_write && address>=18'h04000 && address<18'h08000) sensor_high[address[13:0]]<=write_data[15:0];
        if (accept_write && address>=18'h10000 && address<18'h20000) actuator_inverse[address[15:0]]<=write_data[15:0];
    end
    always @(posedge clk) begin
        if (!rst_n) begin
            write_toggle<=0; config_fault<=0; epoch<=0;
            low_count<=0; high_count<=0; output_count<=0;
            kp<=0; alpha1<=0; alpha2<=0; alpha3<=0;
            lead_alpha<=0; lead_gain<=4096; inverse_power_scale<=1048576;
            low_limits<=32'h3fff0000; high_limits<=32'h3fff0000;
            maximum_fraction<=0; maximum_command<=0;
        end else begin
            write_toggle<=write_address[31];
            if (write_event && !accept_write) config_fault<=1;
            if (accept_write) begin
                config_fault<=0; epoch<=epoch+1;
                if (address<18'h04000)
                    low_count<=address==0 ? 15'd1 : address==low_count ? low_count+1'b1 : 15'd0;
                if (address>=18'h04000 && address<18'h08000)
                    high_count<=address==18'h04000 ? 15'd1 : {1'b0,address[13:0]}==high_count ? high_count+1'b1 : 15'd0;
                if (address>=18'h10000 && address<18'h20000)
                    output_count<=address==18'h10000 ? 17'd1 : {1'b0,address[15:0]}==output_count ? output_count+1'b1 : 17'd0;
                case (address)
                    18'h20000: kp<=write_data[17:0];
                    18'h20001: alpha1<=write_data[19:0];
                    18'h20002: alpha2<=write_data[19:0];
                    18'h20003: alpha3<=write_data[19:0];
                    18'h20004: lead_alpha<=write_data;
                    18'h20005: lead_gain<=write_data[17:0];
                    18'h20006: inverse_power_scale<=write_data[23:0];
                    18'h20007: low_limits<=write_data;
                    18'h20008: high_limits<=write_data;
                    18'h20009: maximum_fraction<=write_data[15:0];
                    18'h2000a: maximum_command<=write_data[15:0]>32767 ? 16'd32767 : write_data[15:0];
                    default: ;
                endcase
            end
        end
    end
    reg [31:0] read_mux;
    always @* begin
        case (address)
            18'h20000: read_mux={{14{kp[17]}},kp};
            18'h20001: read_mux={12'b0,alpha1};
            18'h20002: read_mux={12'b0,alpha2};
            18'h20003: read_mux={12'b0,alpha3};
            18'h20004: read_mux=lead_alpha;
            18'h20005: read_mux={{14{lead_gain[17]}},lead_gain};
            18'h20006: read_mux={8'b0,inverse_power_scale};
            18'h20007: read_mux=low_limits;
            18'h20008: read_mux=high_limits;
            18'h20009: read_mux={16'b0,maximum_fraction};
            18'h2000a: read_mux={16'b0,maximum_command};
            18'h2000b: read_mux=epoch;
            18'h2000c: read_mux={17'b0,low_count};
            18'h2000d: read_mux={17'b0,high_count};
            18'h2000e: read_mux={15'b0,output_count};
            default: read_mux=0;
        endcase
    end
    assign read_data=read_mux;
    assign feature_version=32'h49530301;

    wire signed [15:0] adc=$signed(adc_bus[15:0]);
    wire [13:0] sensor_address=adc<0 ? 14'd0 : adc>16383 ? 14'd16383 : adc[13:0];
    reg [15:0] low_power_read,high_power_read,reference_read;
    reg signed [15:0] adc_read;
    reg valid_read,range_read;
    reg [15:0] low_power,high_power,reference_d;
    reg signed [15:0] adc_d;
    reg valid_d,range_d;
    wire [31:0] sensor_limits=high_mode ? high_limits : low_limits;
    always @(posedge clk) begin
        low_power_read<=sensor_low[sensor_address];
        high_power_read<=sensor_high[sensor_address];
        reference_read<=reference_in; adc_read<=adc;
        valid_read<=rst_n && adc_valid;
        range_read<=adc<0 || {1'b0,adc}<sensor_limits[15:0] || {1'b0,adc}>sensor_limits[31:16];
        // Register the RAM outputs before the error subtraction and Kp DSP.
        // Both sensor banks and all corresponding metadata gain the same clock.
        low_power<=low_power_read; high_power<=high_power_read;
        reference_d<=reference_read; adc_d<=adc_read;
        valid_d<=valid_read; range_d<=range_read;
    end
    wire [15:0] power=high_mode ? high_power : low_power;
    wire signed [16:0] difference=$signed({1'b0,reference_d})-$signed({1'b0,power});
    wire signed [25:0] controller_error={{1{difference[16]}},difference,8'b0};
    wire signed [25:0] feedback;
    wire feedback_valid,controller_saturated;
    wire [31:0] controller_status;
    reg upper_rail,lower_rail;
    reg [15:0] inverse_command_read, inverse_command;
    intensity_compensator controller (
        .clk(clk),.rst_n(rst_n),.enable(active && control[1] && reference_d!=0),
        .state_reset(control[6]),.hold(control[5]),.input_valid(valid_d),
        .error_q8(controller_error),.order(control[8:7]),.kp_q12(kp),
        .alpha1_q24(alpha1),.alpha2_q24(alpha2),.alpha3_q24(alpha3),
        .leadlag_enable(control[4]),.leadlag_alpha_q30(lead_alpha),.leadlag_gain_q12(lead_gain),
        .rail_high(upper_rail || inverse_command>=maximum_command),.rail_low(lower_rail),.feedback_q8(feedback),
        .output_valid(feedback_valid),.saturated(controller_saturated),.status(controller_status));
    // Match feedforward to the fast proportional path (or optional shelf).
    reg [15:0] reference_pipe[0:3];
    integer j;
    always @(posedge clk) begin
        reference_pipe[0]<=reference_d;
        for (j=1;j<4;j=j+1) reference_pipe[j]<=reference_pipe[j-1];
    end
    wire [15:0] ff_reference=control[4] ? reference_pipe[3] : reference_pipe[1];
    wire signed [26:0] ff=control[2] ? $signed({3'b0,ff_reference,8'b0}) : 27'sd0;
    wire signed [26:0] fb=control[1] && feedback_valid ? $signed(feedback) : 27'sd0;
    reg signed [26:0] sum_q8;
    (* use_dsp="yes" *) reg signed [51:0] scaled_product,scaled_product_d;
    reg [15:0] fraction_index;
    wire signed [52:0] rounded_product=$signed(scaled_product_d)+53'sd134217728;
    wire signed [24:0] fraction=rounded_product >>> 28;
    always @(posedge clk) begin
        sum_q8<=ff+fb;
        scaled_product<=sum_q8*$signed({1'b0,inverse_power_scale});
        scaled_product_d<=scaled_product;
        fraction_index<=fraction<0 ? 16'd0 : fraction>maximum_fraction ? maximum_fraction : fraction[15:0];
        upper_rail<=fraction>=maximum_fraction;
        lower_rail<=fraction<=0;
        inverse_command_read<=actuator_inverse[fraction_index];
        // Enable the BRAM output register before the command clamp and rail
        // feedback. The 64K table otherwise cascades eight RAMs plus a compare
        // and the downstream probe mux in one clock. Adds 4.069 ns here only.
        inverse_command<=inverse_command_read;
    end
    // Zero reference is a hard optical-off command, independent of calibration
    // extrapolation or stored integrals. Legacy selection stays bit-for-bit.
    wire [15:0] calibrated_command=inverse_command>maximum_command ? maximum_command : inverse_command;
    assign command_out=!requested ? legacy_command :
        active && (&valid_history) && adc_valid && reference_in!=0 && !control[6] ? calibrated_command : 16'd0;
    assign reference_power=reference_d;
    assign measured_power=power;
    assign raw_adc=adc_d;
    assign error_q8={{6{controller_error[25]}},controller_error};
    wire clip=active && reference_in!=0 && (upper_rail || fraction<0 || inverse_command>maximum_command);
    assign sample_flags={10'b0,(write_event || control_changed), !active, !valid_d,controller_saturated,range_d,clip};
    assign status={20'b0,shot_active,output_loaded,high_loaded,low_loaded,config_fault,
                   valid_d,controller_saturated,range_d,clip,high_mode,ready,active};
endmodule
