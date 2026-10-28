`timescale 1ns/1ps
module intensity_rx_lowpass_tb;
    reg clk=0; always #2 clk=~clk;
    reg rst_n=0, valid=0;
    reg [63:0] i_data=0,q_data=0;
    wire [63:0] out_i,out_q; wire out_valid;
    intensity_rx_lowpass dut(.clk(clk),.rst_n(rst_n),.i_data(i_data),.q_data(q_data),
        .sample_valid(valid),.filtered_i(out_i),.filtered_q(out_q),.filtered_valid(out_valid));
    integer fi,fo,count;
    initial begin
        fi=$fopen("input.txt","r");fo=$fopen("output.txt","w");
        if(!fi || !fo) $fatal(1,"files");
        while(!$feof(fi)) begin
            @(negedge clk);count=$fscanf(fi,"%d %d %h %h\n",rst_n,valid,i_data,q_data);
            if(count!=4) $fatal(1,"input");
            @(posedge clk);#0.1;
            for(integer k=1;k<4;k=k+1) begin
                if(out_i[k*16+:16]!==out_i[15:0] || out_q[k*16+:16]!==out_q[15:0])
                    $fatal(1,"replication");
            end
            $fdisplay(fo,"%d %d %d",out_valid,$signed(out_i[15:0]),$signed(out_q[15:0]));
        end
        $fclose(fi);$fclose(fo);$display("PASS: intensity receive FIR RTL");$finish;
    end
endmodule
