#include "hls_design_meta.h"
const Port_Property HLS_Design_Meta::port_props[]={
	Port_Property("ap_clk", 1, hls_in, -1, "", "", 1),
	Port_Property("ap_rst_n", 1, hls_in, -1, "", "", 1),
	Port_Property("s_axis_cmd_TDATA", 64, hls_in, 0, "axis", "in_data", 1),
	Port_Property("s_axis_cmd_TVALID", 1, hls_in, 3, "axis", "in_vld", 1),
	Port_Property("s_axis_cmd_TREADY", 1, hls_out, 3, "axis", "in_acc", 1),
	Port_Property("s_axis_cmd_TKEEP", 8, hls_in, 1, "axis", "in_data", 1),
	Port_Property("s_axis_cmd_TSTRB", 8, hls_in, 2, "axis", "in_data", 1),
	Port_Property("s_axis_cmd_TLAST", 1, hls_in, 3, "axis", "in_data", 1),
	Port_Property("start_r", 1, hls_in, 4, "ap_none", "in_data", 1),
	Port_Property("fcw_out", 32, hls_out, 5, "ap_none", "out_data", 1),
	Port_Property("active_r", 1, hls_out, 6, "ap_none", "out_data", 1),
	Port_Property("dwell_wait", 1, hls_out, 7, "ap_none", "out_data", 1),
};
const char* HLS_Design_Meta::dut_name = "dwell_fcw_streamer";
