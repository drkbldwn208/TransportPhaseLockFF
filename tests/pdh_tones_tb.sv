`timescale 1ns/1fs
module pdh_tones_tb;
    reg clk=0; always #(1.0e9/(2.0*245760000.0)) clk=~clk;
    reg rst_n=0;
    reg [31:0] control=0, amplitudes=0, reference_coefficients=0;
    wire [31:0] status, feature_version;
    wire [223:0] sum_data;
    wire [127:0] ref_data;
    wire sum_valid,ref_valid;
    reg sum_ready=1,ref_ready=1;
    pdh_tones dut(.clk(clk),.rst_n(rst_n),.control(control),.amplitudes(amplitudes),
        .reference_coefficients(reference_coefficients),.status(status),.feature_version(feature_version),
        .m_sum_tdata(sum_data),.m_sum_tvalid(sum_valid),.m_sum_tready(sum_ready),
        .m_ref_tdata(ref_data),.m_ref_tvalid(ref_valid),.m_ref_tready(ref_ready));
    integer fd, k;
    reg [223:0] held;
    task configure(input integer carrier,sideband,rc,rs);
        begin
            @(negedge clk);
            amplitudes={16'(sideband),16'(carrier)};
            reference_coefficients={16'(rs),16'(rc)};
            control=(control^4)|3;
            repeat(12) @(negedge clk);
            if (status[6:3] || status[2]!=control[2]) $fatal(1,"Commit/fault %h",status);
        end
    endtask
    task record_block(input integer block_id);
        begin
            for(k=0;k<512;k=k+1) begin
                $fwrite(fd,"%d %d %h %h\n",block_id,dut.frame,sum_data,ref_data);
                @(negedge clk);
            end
        end
    endtask
    initial begin
        fd=$fopen("pdh_samples.txt","w");
        repeat(8) @(negedge clk); rst_n=1;
        repeat(8) @(negedge clk);
        if(feature_version!==32'h50444802) $fatal(1,"Incorrect hardware feature version");
        if(sum_data!==0 || ref_data!==0) $fatal(1,"Not muted at reset");
        configure(12000,3000,6000,-8000); record_block(0);
        configure(0,12000,-10000,0); record_block(1);
        configure(12000,0,0,-10000); record_block(2);
        configure(16000,16000,23000,23000); record_block(3);
        // A stall must hold the AXIS word and latch a fault, not silently
        // restart the oscillator at a different frequency or relative phase.
        held=sum_data; sum_ready=0;
        repeat(4) @(negedge clk);
        if(sum_data!==held || !status[4] || ref_data!==0) $fatal(1,"Stall handling %h",status);
        sum_ready=1; repeat(2) @(negedge clk);
        if(sum_data!==0) $fatal(1,"Fault did not mute output");
        control=control^8;
        repeat(12) @(negedge clk);
        if(status[6:3]) $fatal(1,"Fault clear");
        // Amplitudes exceeding total signed headroom cannot silently wrap.
        amplitudes={16'd20000,16'd20000}; control=control^4;
        repeat(12) @(negedge clk);
        if(!status[3] || sum_data!==0 || ref_data!==0) $fatal(1,"Headroom guard");
        $fclose(fd);
        $display("PASS: PDH pipeline, atomic controls, reset mute, headroom and stalls");
        $finish;
    end
endmodule
