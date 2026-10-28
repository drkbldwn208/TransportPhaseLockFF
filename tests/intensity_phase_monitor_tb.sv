`timescale 1ns/1ps
module intensity_phase_monitor_tb;
    reg clk=0;always #2 clk=~clk;
    reg rst_n=0,valid=0;reg [63:0] i_data=0,q_data=0;
    wire [63:0] fi,fq;wire fv;
    intensity_rx_lowpass lowpass(.clk(clk),.rst_n(rst_n),.i_data(i_data),.q_data(q_data),
        .sample_valid(valid),.filtered_i(fi),.filtered_q(fq),.filtered_valid(fv));
    wire [31:0] cartesian;wire cv;
    cordic_average average(.clk(clk),.rst_n(rst_n),.s_axis_i_tdata(fi),.s_axis_q_tdata(fq),
        .s_axis_i_tvalid(fv),.s_axis_q_tvalid(fv),.m_axis_cartesian_tdata(cartesian),.m_axis_cartesian_tvalid(cv));
    wire [55:0] ci_full,cq_full;
    wire [15:0] ci=ci_full[54:39], cq=cq_full[54:39];
    wire [15:0] phase; wire iv,qv,pv;
    design_1_cic_compiler_2_1 cic_i(.aclk(clk),.s_axis_data_tdata(cartesian[15:0]),
        .s_axis_data_tvalid(cv),.s_axis_data_tready(),.m_axis_data_tdata(ci_full),.m_axis_data_tvalid(iv));
    design_1_intensity_cal_q_0 cic_q(.aclk(clk),.s_axis_data_tdata(cartesian[31:16]),
        .s_axis_data_tvalid(cv),.s_axis_data_tready(),.m_axis_data_tdata(cq_full),.m_axis_data_tvalid(qv));
    design_1_cordic_0_0 atan(.aclk(clk),.s_axis_cartesian_tdata({cq,ci}),.s_axis_cartesian_tvalid(iv),
        .m_axis_dout_tdata(phase),.m_axis_dout_tvalid(pv));
    integer fi_handle,fo_handle,count,scenario=0,cycle=0;
    always @(posedge clk) begin
        if(iv!==qv) $fatal(1,"I/Q calibration valid mismatch");
        if(pv) $fdisplay(fo_handle,"%d %d %d %d %d",scenario,cycle,$signed(phase),$signed(ci),$signed(cq));
    end
    initial begin
        fi_handle=$fopen("input.txt","r");fo_handle=$fopen("output.txt","w");
        while(!$feof(fi_handle)) begin
            @(negedge clk);count=$fscanf(fi_handle,"%d %d %d %h %h\n",scenario,rst_n,valid,i_data,q_data);
            if(count!=5) $fatal(1,"input");
            @(posedge clk);#0.1;cycle=cycle+1;
        end
        $fclose(fi_handle);$fclose(fo_handle);$display("PASS: AMD I/Q CIC to CORDIC calibration");$finish;
    end
endmodule
