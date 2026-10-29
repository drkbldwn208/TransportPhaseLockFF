`timescale 1ns/1ps
module intensity_compensator_tb;
    reg clk=0; always #2 clk=~clk;
    reg rst_n=0,enable=0,state_reset=0,hold=0,input_valid=0;
    reg signed [25:0] error_q8=0;
    reg [1:0] order=1;
    reg signed [17:0] kp_q12=0;
    reg [19:0] alpha1_q24=0,alpha2_q24=0,alpha3_q24=0;
    reg leadlag_enable=0;
    reg [31:0] leadlag_alpha_q30=0;
    reg signed [17:0] leadlag_gain_q12=4096;
    reg rail_high=0,rail_low=0;
    wire signed [25:0] feedback_q8;
    wire output_valid,saturated;
    wire [31:0] status;
    intensity_compensator dut(.*);
    integer fi,fo,count;
    initial begin
        fi=$fopen("input.txt","r");fo=$fopen("output.txt","w");
        if(!fi || !fo) $fatal(1,"files");
        while(!$feof(fi)) begin
            @(negedge clk);
            count=$fscanf(fi,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
                rst_n,enable,state_reset,hold,input_valid,error_q8,order,kp_q12,
                alpha1_q24,alpha2_q24,alpha3_q24,leadlag_enable,
                leadlag_alpha_q30,leadlag_gain_q12,rail_high,rail_low);
            if(count!=16) $fatal(1,"input fields %d",count);
            @(posedge clk);#0.1;
            $fdisplay(fo,"%d %d %d %d %d %d %d %d %d",
                feedback_q8,output_valid,saturated,dut.integral1,dut.integral2,
                dut.integral3,dut.phase,dut.p_output,dut.leadlag.state);
        end
        $fclose(fi);$fclose(fo);
        $display("PASS: intensity compensator simulation completed");$finish;
    end
endmodule
