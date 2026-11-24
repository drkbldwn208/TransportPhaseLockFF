`timescale 1ns / 1ps
// Behavioral sin/cos is ONLY for validating the outline's sequencing and
// rotations. It deliberately does not pretend to be AMD's CORDIC RTL model.
module pdh_sincos_model #(parameter LATENCY=7) (
    input wire clk, rst_n, valid, bank,
    input wire signed [25:0] angle,
    output wire valid_out, bank_out,
    output wire signed [23:0] cosine, sine
);
    reg [LATENCY-1:0] valid_pipe, bank_pipe;
    reg signed [23:0] c[0:LATENCY-1], s[0:LATENCY-1];
    real radians;
    function automatic integer rounded(input real value);
        rounded=value>=0 ? $rtoi(value+0.5) : $rtoi(value-0.5);
    endfunction
    always @(posedge clk) begin
        if (!rst_n) begin
            valid_pipe<=0; bank_pipe<=0;
            for (integer k=0;k<LATENCY;k=k+1) begin c[k]<=0; s[k]<=0; end
        end else begin
            radians=$itor($signed(angle))*3.141592653589793/8388608.0;
            c[0]<=rounded($cos(radians)*4194304.0);
            s[0]<=rounded($sin(radians)*4194304.0);
            valid_pipe<={valid_pipe[LATENCY-2:0],valid};
            bank_pipe<={bank_pipe[LATENCY-2:0],bank};
            for (integer k=1;k<LATENCY;k=k+1) begin c[k]<=c[k-1]; s[k]<=s[k-1]; end
        end
    end
    assign cosine=c[LATENCY-1]; assign sine=s[LATENCY-1];
    assign valid_out=valid_pipe[LATENCY-1]; assign bank_out=bank_pipe[LATENCY-1];
endmodule

module pdh_tunable_outline_tb;
    reg clk=0, rst_n=0;
    always #2 clk=~clk;
    reg cfg_write=0, cfg_commit=0;
    reg [6:0] cfg_address=0;
    reg [31:0] cfg_data=0;
    wire busy, ack, fault, phase_valid, bank;
    wire signed [25:0] carrier_angle, modulation_angle;
    wire cv, mv, cb, mb;
    wire signed [23:0] cc, cs, mc, ms;
    wire [223:0] sum_data;
    wire [127:0] reference_data;
    wire sum_valid, reference_valid;
    reg sum_ready=1;
    reg [31:0] configs[0:303];
    integer bank_profile[0:1];
    integer file_out, cycle=0;
    reg [47:0] expected_phase;
    pdh_tunable_outline dut (
        .clk(clk), .rst_n(rst_n), .cfg_write(cfg_write), .cfg_commit(cfg_commit),
        .cfg_address(cfg_address), .cfg_data(cfg_data), .cfg_busy(busy), .cfg_ack(ack), .fault(fault),
        .phase_valid(phase_valid), .phase_bank(bank), .carrier_angle(carrier_angle), .modulation_angle(modulation_angle),
        .carrier_valid(cv), .modulation_valid(mv), .carrier_bank(cb), .modulation_bank(mb),
        .carrier_cos(cc), .carrier_sin(cs), .modulation_cos(mc), .modulation_sin(ms),
        .sum_data(sum_data), .reference_data(reference_data), .sum_valid(sum_valid), .reference_valid(reference_valid),
        .sum_ready(sum_ready), .reference_ready(1'b1)
    );
    pdh_sincos_model carrier (.clk(clk),.rst_n(rst_n),.valid(phase_valid),.bank(bank),.angle(carrier_angle),
        .valid_out(cv),.bank_out(cb),.cosine(cc),.sine(cs));
    pdh_sincos_model modulation (.clk(clk),.rst_n(rst_n),.valid(phase_valid),.bank(bank),.angle(modulation_angle),
        .valid_out(mv),.bank_out(mb),.cosine(mc),.sine(ms));

    task configure(input integer profile);
        begin
            wait(!busy);
            for (integer address=0;address<76;address=address+1) begin
                if (address!=3) begin
                    @(negedge clk); cfg_write=1; cfg_address=address; cfg_data=configs[profile*76+address];
                end
            end
            @(negedge clk); cfg_write=0;
            bank_profile[!bank]=profile;
            cfg_commit=1;
            @(negedge clk); cfg_commit=0;
            wait(!busy);
            repeat(100) @(negedge clk);
        end
    endtask

    always @(posedge clk) begin
        if (rst_n) begin
            expected_phase=dut.phases.carrier_phase+dut.phases.frame_increment;
            $fwrite(file_out,"%0d %h %h %0d ",cycle,carrier_angle,modulation_angle,bank_profile[bank]);
            #1;
            if (dut.phases.carrier_phase!==expected_phase) $fatal(1,"Phase reset/jump at frequency update");
            $fwrite(file_out,"%h %h\n",sum_data,reference_data);
            cycle=cycle+1;
        end
    end
    initial begin
        $readmemh("pdh_tunable_configs.mem",configs);
        bank_profile[0]=-1; bank_profile[1]=-1;
        file_out=$fopen("pdh_tunable_samples.txt","w");
        repeat(5) @(negedge clk); rst_n=1;
        configure(0); configure(1); configure(2); configure(3);
        if (fault) $fatal(1,"Unexpected configuration or streaming fault");
        $fclose(file_out);
        // End logging before the deliberate fault exercise.
        rst_n=0; repeat(3) @(negedge clk); rst_n=1;
        file_out=$fopen("pdh_tunable_fault_samples.txt","w");
        configure(0);
        @(negedge clk); sum_ready=0;
        repeat(3) @(negedge clk);
        if (!fault) $fatal(1,"DAC stall was not detected");
        sum_ready=1;
        repeat(5) @(negedge clk);
        if (sum_data!==0 || reference_data!==0) $fatal(1,"Fault did not mute both outputs");
        $fclose(file_out);
        $display("PASS: phase continuity, coefficient commits, streaming and fault mute");
        $finish;
    end
    initial begin #100000; $fatal(1,"Timeout"); end
endmodule
