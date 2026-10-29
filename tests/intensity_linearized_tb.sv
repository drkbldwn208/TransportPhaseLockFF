`timescale 1ns/1ps
module intensity_linearized_tb;
reg clk=0; always #2 clk=~clk;
reg rst_n=0,adc_valid=1,shot_active=0;
reg [63:0] adc_bus={4{16'd1000}};
reg [15:0] reference_in=4000,legacy_command=1234;
reg [31:0] control=0,write_address=0,write_data=0;
wire [31:0] status,read_data,feature_version;
wire [15:0] command_out,reference_power,measured_power,sample_flags;
wire signed [31:0] error_q8;
wire signed [15:0] raw_adc;
intensity_linearized dut(.*);
integer k;
task tick(input integer n); repeat(n) begin @(posedge clk); #0.1; end endtask
task write_word(input [17:0] a,input [31:0] d);
begin @(negedge clk);write_data=d;tick(2);@(negedge clk);write_address={~write_address[31],13'd0,a};tick(2);end endtask
task check_command(input integer value);begin tick(25);if(command_out!==value) $fatal(1,"command %d expected %d",command_out,value);end endtask
initial begin
 tick(5);rst_n=1;tick(5);
 if(command_out!=1234 || status[10:8]!=0) $fatal(1,"legacy/reset");
 control=5;check_command(0);control=0;
 for(k=0;k<16384;k=k+1) write_word(k,k*2);
 for(k=0;k<16384;k=k+1) write_word(18'h04000+k,k*4);
 for(k=0;k<65536;k=k+1) write_word(18'h10000+k,k/2);
 if(status[10:8]!=7) $fatal(1,"tables not loaded %h",status);
 write_word(18'h20000,4096);
 write_word(18'h20007,32'h2710000a);write_word(18'h20008,32'h2710000a);
 write_word(18'h20009,65535);write_word(18'h2000a,32767);
 control=133;check_command(2000); // FF only PI order1
 if(measured_power!=2000 || error_q8!=512000) $fatal(1,"sensor/error");
 // A simultaneous optical-reference/ADC change must retain matched timestamps.
 @(negedge clk);reference_in=5000;adc_bus={4{16'd2000}};
 tick(1);if(reference_power!=4000 || measured_power!=2000 || raw_adc!=1000)
     $fatal(1,"sensor metadata changed before registered RAM output");
 tick(1);if(reference_power!=5000 || measured_power!=4000 || raw_adc!=2000 || error_q8!=256000)
     $fatal(1,"sensor/reference/error alignment");
 reference_in=4000;adc_bus={4{16'd1000}};check_command(2000);
 // From an input sampled on edge 1, calibrated command changes on edge 10:
 // sensor read/output, aligned FF/P, sum, scale, index, RAM read/output.
 @(negedge clk);reference_in=5000;
 for(k=1;k<10;k=k+1) begin tick(1);if(command_out!=2000) $fatal(1,"FF early edge %d",k);end
 tick(1);if(command_out!=2500) $fatal(1,"FF latency");
 control=149;check_command(2500); // optional shelf adds two clocks to FF alignment
 @(negedge clk);reference_in=6000;
 for(k=1;k<12;k=k+1) begin tick(1);if(command_out!=2500) $fatal(1,"shelf FF early edge %d",k);end
 tick(1);if(command_out!=3000) $fatal(1,"shelf FF latency");
 reference_in=4000;control=133;check_command(2000);
 control=135;check_command(3000); // FF + pure P, unitygain
 write_word(18'h20000,0); // active update must be refused
 if(!status[7] || read_data!=4096) $fatal(1,"livewrite not blocked");
 control=0;write_word(18'h20006,2097152);control=135;check_command(6000);
 control=143;check_command(4000); // high mode: measured4000,zeroerror
 if(measured_power!=4000) $fatal(1,"mode lookup");
 reference_in=0;tick(1);if(command_out!=0) $fatal(1,"opticaloff");
 tick(25);reference_in=4000;check_command(4000);
 adc_valid=0;tick(1);if(command_out!=0) $fatal(1,"ADCinvalid");adc_valid=1;check_command(4000);
 adc_bus={4{16'd15000}};tick(4);if(!sample_flags[1]) $fatal(1,"calrange");
 adc_bus={4{16'd1000}};control=0;shot_active=1;write_word(18'h20000,0);
 if(!status[7] || read_data!=4096) $fatal(1,"shotwrite notblocked");
 shot_active=0;write_word(18'h20000,4096);
 // Partial reload invalidates the bank; never read uncalibrated RAM live.
 write_word(0,0);control=133;check_command(0);
 if(feature_version!=32'h49530301) $fatal(1,"version");
 $display("PASS intensity linearized tables, FF, gain/sign, mode, rails, write guards, legacy and opticaloff");
 $finish;
end
endmodule
