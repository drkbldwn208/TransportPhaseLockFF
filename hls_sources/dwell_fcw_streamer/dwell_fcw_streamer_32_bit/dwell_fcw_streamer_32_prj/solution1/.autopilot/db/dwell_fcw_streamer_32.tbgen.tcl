set moduleName dwell_fcw_streamer_32
set isTopModule 1
set isCombinational 0
set isDatapathOnly 0
set isPipelined 0
set pipeline_type function
set FunctionProtocol ap_ctrl_none
set isOneStateSeq 1
set ProfileFlag 0
set StallSigGenFlag 0
set isEnableWaveformDebug 1
set hasInterrupt 0
set DLRegFirstOffset 0
set DLRegItemOffset 0
set C_modelName {dwell_fcw_streamer_32}
set C_modelType { void 0 }
set ap_memory_interface_dict [dict create]
set C_modelArgList {
	{ s_axis_cmd_V_data_V int 32 regular {axi_s 0 volatile  { s_axis_cmd Data } }  }
	{ s_axis_cmd_V_keep_V int 4 regular {axi_s 0 volatile  { s_axis_cmd Keep } }  }
	{ s_axis_cmd_V_strb_V int 4 regular {axi_s 0 volatile  { s_axis_cmd Strb } }  }
	{ s_axis_cmd_V_last_V int 1 regular {axi_s 0 volatile  { s_axis_cmd Last } }  }
	{ start_r uint 1 regular  }
	{ fcw_out int 16 regular {pointer 1}  }
	{ active_r int 1 regular {pointer 1}  }
	{ dwell_wait int 1 regular {pointer 1}  }
}
set hasAXIMCache 0
set hasAXIML2Cache 0
set AXIMCacheInstDict [dict create]
set C_modelArgMapList {[ 
	{ "Name" : "s_axis_cmd_V_data_V", "interface" : "axis", "bitwidth" : 32, "direction" : "READONLY"} , 
 	{ "Name" : "s_axis_cmd_V_keep_V", "interface" : "axis", "bitwidth" : 4, "direction" : "READONLY"} , 
 	{ "Name" : "s_axis_cmd_V_strb_V", "interface" : "axis", "bitwidth" : 4, "direction" : "READONLY"} , 
 	{ "Name" : "s_axis_cmd_V_last_V", "interface" : "axis", "bitwidth" : 1, "direction" : "READONLY"} , 
 	{ "Name" : "start_r", "interface" : "wire", "bitwidth" : 1, "direction" : "READONLY"} , 
 	{ "Name" : "fcw_out", "interface" : "wire", "bitwidth" : 16, "direction" : "WRITEONLY"} , 
 	{ "Name" : "active_r", "interface" : "wire", "bitwidth" : 1, "direction" : "WRITEONLY"} , 
 	{ "Name" : "dwell_wait", "interface" : "wire", "bitwidth" : 1, "direction" : "WRITEONLY"} ]}
# RTL Port declarations: 
set portNum 12
set portList { 
	{ ap_clk sc_in sc_logic 1 clock -1 } 
	{ ap_rst_n sc_in sc_logic 1 reset -1 active_low_sync } 
	{ s_axis_cmd_TDATA sc_in sc_lv 32 signal 0 } 
	{ s_axis_cmd_TVALID sc_in sc_logic 1 invld 3 } 
	{ s_axis_cmd_TREADY sc_out sc_logic 1 inacc 3 } 
	{ s_axis_cmd_TKEEP sc_in sc_lv 4 signal 1 } 
	{ s_axis_cmd_TSTRB sc_in sc_lv 4 signal 2 } 
	{ s_axis_cmd_TLAST sc_in sc_lv 1 signal 3 } 
	{ start_r sc_in sc_lv 1 signal 4 } 
	{ fcw_out sc_out sc_lv 16 signal 5 } 
	{ active_r sc_out sc_lv 1 signal 6 } 
	{ dwell_wait sc_out sc_lv 1 signal 7 } 
}
set NewPortList {[ 
	{ "name": "ap_clk", "direction": "in", "datatype": "sc_logic", "bitwidth":1, "type": "clock", "bundle":{"name": "ap_clk", "role": "default" }} , 
 	{ "name": "ap_rst_n", "direction": "in", "datatype": "sc_logic", "bitwidth":1, "type": "reset", "bundle":{"name": "ap_rst_n", "role": "default" }} , 
 	{ "name": "s_axis_cmd_TDATA", "direction": "in", "datatype": "sc_lv", "bitwidth":32, "type": "signal", "bundle":{"name": "s_axis_cmd_V_data_V", "role": "default" }} , 
 	{ "name": "s_axis_cmd_TVALID", "direction": "in", "datatype": "sc_logic", "bitwidth":1, "type": "invld", "bundle":{"name": "s_axis_cmd_V_last_V", "role": "default" }} , 
 	{ "name": "s_axis_cmd_TREADY", "direction": "out", "datatype": "sc_logic", "bitwidth":1, "type": "inacc", "bundle":{"name": "s_axis_cmd_V_last_V", "role": "default" }} , 
 	{ "name": "s_axis_cmd_TKEEP", "direction": "in", "datatype": "sc_lv", "bitwidth":4, "type": "signal", "bundle":{"name": "s_axis_cmd_V_keep_V", "role": "default" }} , 
 	{ "name": "s_axis_cmd_TSTRB", "direction": "in", "datatype": "sc_lv", "bitwidth":4, "type": "signal", "bundle":{"name": "s_axis_cmd_V_strb_V", "role": "default" }} , 
 	{ "name": "s_axis_cmd_TLAST", "direction": "in", "datatype": "sc_lv", "bitwidth":1, "type": "signal", "bundle":{"name": "s_axis_cmd_V_last_V", "role": "default" }} , 
 	{ "name": "start_r", "direction": "in", "datatype": "sc_lv", "bitwidth":1, "type": "signal", "bundle":{"name": "start_r", "role": "default" }} , 
 	{ "name": "fcw_out", "direction": "out", "datatype": "sc_lv", "bitwidth":16, "type": "signal", "bundle":{"name": "fcw_out", "role": "default" }} , 
 	{ "name": "active_r", "direction": "out", "datatype": "sc_lv", "bitwidth":1, "type": "signal", "bundle":{"name": "active_r", "role": "default" }} , 
 	{ "name": "dwell_wait", "direction": "out", "datatype": "sc_lv", "bitwidth":1, "type": "signal", "bundle":{"name": "dwell_wait", "role": "default" }}  ]}

set RtlHierarchyInfo {[
	{"ID" : "0", "Level" : "0", "Path" : "`AUTOTB_DUT_INST", "Parent" : "", "Child" : ["1", "2", "3", "4"],
		"CDFG" : "dwell_fcw_streamer_32",
		"Protocol" : "ap_ctrl_none",
		"ControlExist" : "0", "ap_start" : "0", "ap_ready" : "0", "ap_done" : "0", "ap_continue" : "0", "ap_idle" : "0", "real_start" : "0",
		"Pipeline" : "None", "UnalignedPipeline" : "0", "RewindPipeline" : "0", "ProcessNetwork" : "0",
		"II" : "1",
		"VariableLatency" : "0", "ExactLatency" : "0", "EstimateLatencyMin" : "0", "EstimateLatencyMax" : "0",
		"Combinational" : "0",
		"Datapath" : "0",
		"ClockEnable" : "0",
		"HasSubDataflow" : "0",
		"InDataflowNetwork" : "0",
		"HasNonBlockingOperation" : "0",
		"IsBlackBox" : "0",
		"Port" : [
			{"Name" : "s_axis_cmd_V_data_V", "Type" : "Axis", "Direction" : "I", "BaseName" : "s_axis_cmd",
				"BlockSignal" : [
					{"Name" : "s_axis_cmd_TDATA_blk_n", "Type" : "RtlSignal"}]},
			{"Name" : "s_axis_cmd_V_keep_V", "Type" : "Axis", "Direction" : "I", "BaseName" : "s_axis_cmd"},
			{"Name" : "s_axis_cmd_V_strb_V", "Type" : "Axis", "Direction" : "I", "BaseName" : "s_axis_cmd"},
			{"Name" : "s_axis_cmd_V_last_V", "Type" : "Axis", "Direction" : "I", "BaseName" : "s_axis_cmd"},
			{"Name" : "start_r", "Type" : "None", "Direction" : "I"},
			{"Name" : "fcw_out", "Type" : "None", "Direction" : "O"},
			{"Name" : "active_r", "Type" : "None", "Direction" : "O"},
			{"Name" : "dwell_wait", "Type" : "None", "Direction" : "O"},
			{"Name" : "current_fcw", "Type" : "OVld", "Direction" : "IO"},
			{"Name" : "state", "Type" : "OVld", "Direction" : "IO"},
			{"Name" : "dwell_remaining", "Type" : "OVld", "Direction" : "IO"},
			{"Name" : "start_d", "Type" : "OVld", "Direction" : "IO"},
			{"Name" : "current_word_was_last", "Type" : "OVld", "Direction" : "IO"}]},
	{"ID" : "1", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.regslice_both_s_axis_cmd_V_data_V_U", "Parent" : "0"},
	{"ID" : "2", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.regslice_both_s_axis_cmd_V_keep_V_U", "Parent" : "0"},
	{"ID" : "3", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.regslice_both_s_axis_cmd_V_strb_V_U", "Parent" : "0"},
	{"ID" : "4", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.regslice_both_s_axis_cmd_V_last_V_U", "Parent" : "0"}]}


set ArgLastReadFirstWriteLatency {
	dwell_fcw_streamer_32 {
		s_axis_cmd_V_data_V {Type I LastRead 0 FirstWrite -1}
		s_axis_cmd_V_keep_V {Type I LastRead 0 FirstWrite -1}
		s_axis_cmd_V_strb_V {Type I LastRead 0 FirstWrite -1}
		s_axis_cmd_V_last_V {Type I LastRead 0 FirstWrite -1}
		start_r {Type I LastRead 0 FirstWrite -1}
		fcw_out {Type O LastRead -1 FirstWrite 0}
		active_r {Type O LastRead -1 FirstWrite 0}
		dwell_wait {Type O LastRead -1 FirstWrite 0}
		current_fcw {Type IO LastRead -1 FirstWrite -1}
		state {Type IO LastRead -1 FirstWrite -1}
		dwell_remaining {Type IO LastRead -1 FirstWrite -1}
		start_d {Type IO LastRead -1 FirstWrite -1}
		current_word_was_last {Type IO LastRead -1 FirstWrite -1}}}

set hasDtUnsupportedChannel 0

set PerformanceInfo {[
	{"Name" : "Latency", "Min" : "0", "Max" : "0"}
	, {"Name" : "Interval", "Min" : "1", "Max" : "1"}
]}

set PipelineEnableSignalInfo {[
]}

set Spec2ImplPortList { 
	s_axis_cmd_V_data_V { axis {  { s_axis_cmd_TDATA in_data 0 32 } } }
	s_axis_cmd_V_keep_V { axis {  { s_axis_cmd_TKEEP in_data 0 4 } } }
	s_axis_cmd_V_strb_V { axis {  { s_axis_cmd_TSTRB in_data 0 4 } } }
	s_axis_cmd_V_last_V { axis {  { s_axis_cmd_TVALID in_vld 0 1 }  { s_axis_cmd_TREADY in_acc 1 1 }  { s_axis_cmd_TLAST in_data 0 1 } } }
	start_r { ap_none {  { start_r in_data 0 1 } } }
	fcw_out { ap_none {  { fcw_out out_data 1 16 } } }
	active_r { ap_none {  { active_r out_data 1 1 } } }
	dwell_wait { ap_none {  { dwell_wait out_data 1 1 } } }
}

set maxi_interface_dict [dict create]

# RTL port scheduling information:
set fifoSchedulingInfoList { 
}

# RTL bus port read request latency information:
set busReadReqLatencyList { 
}

# RTL bus port write response latency information:
set busWriteResLatencyList { 
}

# RTL array port load latency information:
set memoryLoadLatencyList { 
}
