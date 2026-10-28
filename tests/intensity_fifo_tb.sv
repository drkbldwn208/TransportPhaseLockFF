`timescale 1ns/1ps
// Probe + the GENERATED Xilinx FIFO netlist: reset recovery and frame continuity.
module intensity_fifo_tb;
    reg clk=0; always #2 clk=~clk;
    reg rst_n=0, dma_ready=1;
    reg [15:0] tag=0;
    always @(posedge clk) tag<=tag+1'b1;
    reg [31:0] control=0;
    wire [127:0] tx_data,rx_data;
    wire tx_valid,tx_ready,tx_last,rx_valid,rx_last,fifo_reset;
    wire [31:0] status;
    intensity_probe probe(.clk(clk),.rst_n(rst_n),.adc_bus({4{tag}}),.adc_rail_bus({4{tag}}),.adc_valid(1'b1),
        .dac_ready(1'b1),.controller_command(16'd10000),.manual_command(16'd0),.manual_enable(1'b0),
        .command_out(),.control(control),.frequency_word(32'd0),.amplitude_word(32'd0),
        .limits(32'h7fff0000),.status(status),.feature_version(),.clip_samples(),.invalid_samples(),
        .fifo_rst_n(fifo_reset),.m_axis_tdata(tx_data),.m_axis_tvalid(tx_valid),
        .m_axis_tlast(tx_last),.m_axis_tready(tx_ready));
    design_1_intensity_fifo_0 fifo(.s_axis_aclk(clk),.s_axis_aresetn(fifo_reset),
        .s_axis_tdata(tx_data),.s_axis_tvalid(tx_valid),.s_axis_tready(tx_ready),.s_axis_tlast(tx_last),
        .m_axis_tdata(rx_data),.m_axis_tvalid(rx_valid),.m_axis_tready(dma_ready),.m_axis_tlast(rx_last));
    integer records=0, spacing=8, previous_tag=0;
    always @(posedge clk) if(rx_valid && dma_ready) begin
        if(records && rx_data[15:0]-previous_tag!=spacing) $fatal(1,"nonuniform FIFO capture");
        previous_tag=rx_data[15:0];records=records+1;
        if(rx_last && records!=64) $fatal(1,"wrong FIFO TLAST");
    end
    integer test;
    initial begin
        repeat(100) @(negedge clk);rst_n=1;
        for(test=0;test<3;test=test+1) begin
            repeat(32) @(negedge clk);
            records=0;spacing=test==2 ? 256 : 8;
            dma_ready=test!=1;
            control=(64<<12)|((test==2 ? 8 : 3)<<3)|2;
            if(test==1) begin repeat(400) @(negedge clk);dma_ready=1;end
            wait(records==64);@(negedge clk);
            if(status[9:2]!=0 || !status[1]) $fatal(1,"FIFO startup fault %h",status);
            control=0;
        end
        $display("PASS: generated Xilinx FIFO reset/rearm, D=3 and D=8 frame spacing, DMA backpressure, all records/TLAST");
        $finish;
    end
    initial begin #200000;$fatal(1,"FIFO timeout");end
endmodule
