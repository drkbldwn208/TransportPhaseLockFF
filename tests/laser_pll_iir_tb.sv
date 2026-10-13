`timescale 1ns/1ps
module laser_pll_iir_tb;
    reg clk=0; always #2.0345 clk=~clk;
    reg rst_n=0, valid=1, input_saturated=0;
    reg signed [15:0] x=0;
    reg [31:0] control=0,b0=134217728,b1=0,pole=0;
    wire signed [15:0] y;
    wire yvalid, saturated;
    wire [31:0] status;
    laser_pll_iir dut(.clk(clk),.rst_n(rst_n),.input_code(x),.input_valid(valid),
        .input_saturated(input_saturated),.control(control),.b0_word(b0),.b1_word(b1),.pole_word(pole),
        .output_code(y),.output_valid(yvalid),.output_saturated(saturated),.status(status));
    integer f;
    initial begin
        f=$fopen("iir_trace.txt","w");
        repeat(4) @(negedge clk); rst_n=1;
        // Prove bypass before any RF edge, including valid/saturation propagation.
        x=-1234; #0.1;
        if(y!==x || yvalid!==valid) $fatal(1,"bypass has latency");
        input_saturated=1; #0.1; if(!saturated) $fatal(1,"bypass lost saturation");
        input_saturated=0;
        // Unity-DC phase lead, p=0.99, b0=2, b1=-1.99 (rounded Q5.27).
        b0=268435456; b1=-267093279; pole=2126008800;
        control=2; @(negedge clk); control=3;
        for(integer j=0;j<60000;j=j+1) begin
            x=$rtoi(-3000+1700*$sin(6.283185307179586*960000*j/245760000.0));
            $fwrite(f,"%d %d ",dut.phase,x);
            @(negedge clk);
            $fdisplay(f,"%d %d %d",y,yvalid,saturated);
        end
        // A clipped input in either half of a pair must propagate its flag.
        while(dut.phase!=1) @(negedge clk);
        input_saturated=1; @(negedge clk); input_saturated=0;
        repeat(2) @(negedge clk);
        if(!saturated) $fatal(1,"previous half-pair saturation was lost");
        repeat(4) @(negedge clk);
        // Unstable coefficients are rejected in Python. Hardware must always
        // saturate, never wrap, even with a deliberate large finite gain.
        control=0; b0=1073741824; b1=0; pole=0; x=20000;
        control=0; @(negedge clk); // toggle commit back to 0
        control=1; repeat(10) @(negedge clk);
        if(y!=32767 || !saturated) $fatal(1,"positive overflow did not saturate");
        x=-20000; repeat(10) @(negedge clk);
        if(y!=-32768 || !saturated) $fatal(1,"negative overflow did not saturate");
        control=0; #0.1; if(y!==x) $fatal(1,"return to bypass delayed");
        $fclose(f); $display("PASS: IIR zero-cycle bypass, commit, signed tone, saturation"); $finish;
    end
endmodule
