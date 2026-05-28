set moduleName rfdc_iq_derotator
set isTopModule 1
set isCombinational 0
set isDatapathOnly 0
set isPipelined 1
set pipeline_type function
set FunctionProtocol ap_ctrl_none
set isOneStateSeq 0
set ProfileFlag 0
set StallSigGenFlag 0
set isEnableWaveformDebug 1
set hasInterrupt 0
set DLRegFirstOffset 0
set DLRegItemOffset 0
set C_modelName {rfdc_iq_derotator}
set C_modelType { void 0 }
set ap_memory_interface_dict [dict create]
set C_modelArgList {
	{ s_axis_i int 128 regular {axi_s 0 volatile  { s_axis_i Data } }  }
	{ s_axis_q int 128 regular {axi_s 0 volatile  { s_axis_q Data } }  }
	{ m_axis_i int 128 regular {axi_s 1 volatile  { m_axis_i Data } }  }
	{ m_axis_q int 128 regular {axi_s 1 volatile  { m_axis_q Data } }  }
	{ enable uint 1 regular  }
	{ reset_phase uint 1 regular  }
	{ phase_offset int 32 regular  }
}
set hasAXIMCache 0
set hasAXIML2Cache 0
set AXIMCacheInstDict [dict create]
set C_modelArgMapList {[ 
	{ "Name" : "s_axis_i", "interface" : "axis", "bitwidth" : 128, "direction" : "READONLY"} , 
 	{ "Name" : "s_axis_q", "interface" : "axis", "bitwidth" : 128, "direction" : "READONLY"} , 
 	{ "Name" : "m_axis_i", "interface" : "axis", "bitwidth" : 128, "direction" : "WRITEONLY"} , 
 	{ "Name" : "m_axis_q", "interface" : "axis", "bitwidth" : 128, "direction" : "WRITEONLY"} , 
 	{ "Name" : "enable", "interface" : "wire", "bitwidth" : 1, "direction" : "READONLY"} , 
 	{ "Name" : "reset_phase", "interface" : "wire", "bitwidth" : 1, "direction" : "READONLY"} , 
 	{ "Name" : "phase_offset", "interface" : "wire", "bitwidth" : 32, "direction" : "READONLY"} ]}
# RTL Port declarations: 
set portNum 17
set portList { 
	{ ap_clk sc_in sc_logic 1 clock -1 } 
	{ ap_rst_n sc_in sc_logic 1 reset -1 active_low_sync } 
	{ s_axis_i_TDATA sc_in sc_lv 128 signal 0 } 
	{ s_axis_i_TVALID sc_in sc_logic 1 invld 0 } 
	{ s_axis_i_TREADY sc_out sc_logic 1 inacc 0 } 
	{ s_axis_q_TDATA sc_in sc_lv 128 signal 1 } 
	{ s_axis_q_TVALID sc_in sc_logic 1 invld 1 } 
	{ s_axis_q_TREADY sc_out sc_logic 1 inacc 1 } 
	{ m_axis_i_TDATA sc_out sc_lv 128 signal 2 } 
	{ m_axis_i_TVALID sc_out sc_logic 1 outvld 2 } 
	{ m_axis_i_TREADY sc_in sc_logic 1 outacc 2 } 
	{ m_axis_q_TDATA sc_out sc_lv 128 signal 3 } 
	{ m_axis_q_TVALID sc_out sc_logic 1 outvld 3 } 
	{ m_axis_q_TREADY sc_in sc_logic 1 outacc 3 } 
	{ enable sc_in sc_lv 1 signal 4 } 
	{ reset_phase sc_in sc_lv 1 signal 5 } 
	{ phase_offset sc_in sc_lv 32 signal 6 } 
}
set NewPortList {[ 
	{ "name": "ap_clk", "direction": "in", "datatype": "sc_logic", "bitwidth":1, "type": "clock", "bundle":{"name": "ap_clk", "role": "default" }} , 
 	{ "name": "ap_rst_n", "direction": "in", "datatype": "sc_logic", "bitwidth":1, "type": "reset", "bundle":{"name": "ap_rst_n", "role": "default" }} , 
 	{ "name": "s_axis_i_TDATA", "direction": "in", "datatype": "sc_lv", "bitwidth":128, "type": "signal", "bundle":{"name": "s_axis_i", "role": "TDATA" }} , 
 	{ "name": "s_axis_i_TVALID", "direction": "in", "datatype": "sc_logic", "bitwidth":1, "type": "invld", "bundle":{"name": "s_axis_i", "role": "TVALID" }} , 
 	{ "name": "s_axis_i_TREADY", "direction": "out", "datatype": "sc_logic", "bitwidth":1, "type": "inacc", "bundle":{"name": "s_axis_i", "role": "TREADY" }} , 
 	{ "name": "s_axis_q_TDATA", "direction": "in", "datatype": "sc_lv", "bitwidth":128, "type": "signal", "bundle":{"name": "s_axis_q", "role": "TDATA" }} , 
 	{ "name": "s_axis_q_TVALID", "direction": "in", "datatype": "sc_logic", "bitwidth":1, "type": "invld", "bundle":{"name": "s_axis_q", "role": "TVALID" }} , 
 	{ "name": "s_axis_q_TREADY", "direction": "out", "datatype": "sc_logic", "bitwidth":1, "type": "inacc", "bundle":{"name": "s_axis_q", "role": "TREADY" }} , 
 	{ "name": "m_axis_i_TDATA", "direction": "out", "datatype": "sc_lv", "bitwidth":128, "type": "signal", "bundle":{"name": "m_axis_i", "role": "TDATA" }} , 
 	{ "name": "m_axis_i_TVALID", "direction": "out", "datatype": "sc_logic", "bitwidth":1, "type": "outvld", "bundle":{"name": "m_axis_i", "role": "TVALID" }} , 
 	{ "name": "m_axis_i_TREADY", "direction": "in", "datatype": "sc_logic", "bitwidth":1, "type": "outacc", "bundle":{"name": "m_axis_i", "role": "TREADY" }} , 
 	{ "name": "m_axis_q_TDATA", "direction": "out", "datatype": "sc_lv", "bitwidth":128, "type": "signal", "bundle":{"name": "m_axis_q", "role": "TDATA" }} , 
 	{ "name": "m_axis_q_TVALID", "direction": "out", "datatype": "sc_logic", "bitwidth":1, "type": "outvld", "bundle":{"name": "m_axis_q", "role": "TVALID" }} , 
 	{ "name": "m_axis_q_TREADY", "direction": "in", "datatype": "sc_logic", "bitwidth":1, "type": "outacc", "bundle":{"name": "m_axis_q", "role": "TREADY" }} , 
 	{ "name": "enable", "direction": "in", "datatype": "sc_lv", "bitwidth":1, "type": "signal", "bundle":{"name": "enable", "role": "default" }} , 
 	{ "name": "reset_phase", "direction": "in", "datatype": "sc_lv", "bitwidth":1, "type": "signal", "bundle":{"name": "reset_phase", "role": "default" }} , 
 	{ "name": "phase_offset", "direction": "in", "datatype": "sc_lv", "bitwidth":32, "type": "signal", "bundle":{"name": "phase_offset", "role": "default" }}  ]}

set RtlHierarchyInfo {[
	{"ID" : "0", "Level" : "0", "Path" : "`AUTOTB_DUT_INST", "Parent" : "", "Child" : ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38"],
		"CDFG" : "rfdc_iq_derotator",
		"Protocol" : "ap_ctrl_none",
		"ControlExist" : "0", "ap_start" : "0", "ap_ready" : "0", "ap_done" : "0", "ap_continue" : "0", "ap_idle" : "0", "real_start" : "0",
		"Pipeline" : "Aligned", "UnalignedPipeline" : "0", "RewindPipeline" : "0", "ProcessNetwork" : "0",
		"II" : "1",
		"VariableLatency" : "0", "ExactLatency" : "8", "EstimateLatencyMin" : "8", "EstimateLatencyMax" : "8",
		"Combinational" : "0",
		"Datapath" : "0",
		"ClockEnable" : "0",
		"HasSubDataflow" : "0",
		"InDataflowNetwork" : "0",
		"HasNonBlockingOperation" : "0",
		"IsBlackBox" : "0",
		"Port" : [
			{"Name" : "s_axis_i", "Type" : "Axis", "Direction" : "I",
				"BlockSignal" : [
					{"Name" : "s_axis_i_TDATA_blk_n", "Type" : "RtlSignal"}]},
			{"Name" : "s_axis_q", "Type" : "Axis", "Direction" : "I",
				"BlockSignal" : [
					{"Name" : "s_axis_q_TDATA_blk_n", "Type" : "RtlSignal"}]},
			{"Name" : "m_axis_i", "Type" : "Axis", "Direction" : "O",
				"BlockSignal" : [
					{"Name" : "m_axis_i_TDATA_blk_n", "Type" : "RtlSignal"}]},
			{"Name" : "m_axis_q", "Type" : "Axis", "Direction" : "O",
				"BlockSignal" : [
					{"Name" : "m_axis_q_TDATA_blk_n", "Type" : "RtlSignal"}]},
			{"Name" : "enable", "Type" : "None", "Direction" : "I"},
			{"Name" : "reset_phase", "Type" : "None", "Direction" : "I"},
			{"Name" : "phase_offset", "Type" : "None", "Direction" : "I"},
			{"Name" : "phase_acc", "Type" : "OVld", "Direction" : "IO"},
			{"Name" : "RFDC_IQ_DEROTATOR_SINE_LUT", "Type" : "Memory", "Direction" : "I"}]},
	{"ID" : "1", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.RFDC_IQ_DEROTATOR_SINE_LUT_U", "Parent" : "0"},
	{"ID" : "2", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U1", "Parent" : "0"},
	{"ID" : "3", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U2", "Parent" : "0"},
	{"ID" : "4", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U3", "Parent" : "0"},
	{"ID" : "5", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U4", "Parent" : "0"},
	{"ID" : "6", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U5", "Parent" : "0"},
	{"ID" : "7", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U6", "Parent" : "0"},
	{"ID" : "8", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U7", "Parent" : "0"},
	{"ID" : "9", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U8", "Parent" : "0"},
	{"ID" : "10", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U9", "Parent" : "0"},
	{"ID" : "11", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U10", "Parent" : "0"},
	{"ID" : "12", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U11", "Parent" : "0"},
	{"ID" : "13", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U12", "Parent" : "0"},
	{"ID" : "14", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U13", "Parent" : "0"},
	{"ID" : "15", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U14", "Parent" : "0"},
	{"ID" : "16", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U15", "Parent" : "0"},
	{"ID" : "17", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mul_16s_16s_32_1_1_U16", "Parent" : "0"},
	{"ID" : "18", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.sparsemux_7_2_16_1_1_U17", "Parent" : "0"},
	{"ID" : "19", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_muladd_16s_16s_32s_32_4_1_U18", "Parent" : "0"},
	{"ID" : "20", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_mulsub_16s_16s_32s_32_4_1_U19", "Parent" : "0"},
	{"ID" : "21", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_muladd_16s_16s_32s_32_4_1_U20", "Parent" : "0"},
	{"ID" : "22", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_mulsub_16s_16s_32s_32_4_1_U21", "Parent" : "0"},
	{"ID" : "23", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_muladd_16s_16s_32s_32_4_1_U22", "Parent" : "0"},
	{"ID" : "24", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_mulsub_16s_16s_32s_32_4_1_U23", "Parent" : "0"},
	{"ID" : "25", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_muladd_16s_16s_32s_32_4_1_U24", "Parent" : "0"},
	{"ID" : "26", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_mulsub_16s_16s_32s_32_4_1_U25", "Parent" : "0"},
	{"ID" : "27", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_muladd_16s_16s_32s_32_4_1_U26", "Parent" : "0"},
	{"ID" : "28", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_mulsub_16s_16s_32s_32_4_1_U27", "Parent" : "0"},
	{"ID" : "29", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_muladd_16s_16s_32s_32_4_1_U28", "Parent" : "0"},
	{"ID" : "30", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_mulsub_16s_16s_32s_32_4_1_U29", "Parent" : "0"},
	{"ID" : "31", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_muladd_16s_16s_32s_32_4_1_U30", "Parent" : "0"},
	{"ID" : "32", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_mulsub_16s_16s_32s_32_4_1_U31", "Parent" : "0"},
	{"ID" : "33", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_muladd_16s_16s_32s_32_4_1_U32", "Parent" : "0"},
	{"ID" : "34", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.mac_mulsub_16s_16s_32s_32_4_1_U33", "Parent" : "0"},
	{"ID" : "35", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.regslice_both_s_axis_i_U", "Parent" : "0"},
	{"ID" : "36", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.regslice_both_s_axis_q_U", "Parent" : "0"},
	{"ID" : "37", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.regslice_both_m_axis_i_U", "Parent" : "0"},
	{"ID" : "38", "Level" : "1", "Path" : "`AUTOTB_DUT_INST.regslice_both_m_axis_q_U", "Parent" : "0"}]}


set ArgLastReadFirstWriteLatency {
	rfdc_iq_derotator {
		s_axis_i {Type I LastRead 0 FirstWrite -1}
		s_axis_q {Type I LastRead 0 FirstWrite -1}
		m_axis_i {Type O LastRead -1 FirstWrite 7}
		m_axis_q {Type O LastRead -1 FirstWrite 7}
		enable {Type I LastRead 0 FirstWrite -1}
		reset_phase {Type I LastRead 0 FirstWrite -1}
		phase_offset {Type I LastRead 0 FirstWrite -1}
		phase_acc {Type IO LastRead -1 FirstWrite -1}
		RFDC_IQ_DEROTATOR_SINE_LUT {Type I LastRead -1 FirstWrite -1}}}

set hasDtUnsupportedChannel 0

set PerformanceInfo {[
	{"Name" : "Latency", "Min" : "8", "Max" : "8"}
	, {"Name" : "Interval", "Min" : "1", "Max" : "1"}
]}

set PipelineEnableSignalInfo {[
	{"Pipeline" : "0", "EnableSignal" : "ap_enable_pp0"}
]}

set Spec2ImplPortList { 
	s_axis_i { axis {  { s_axis_i_TDATA in_data 0 128 }  { s_axis_i_TVALID in_vld 0 1 }  { s_axis_i_TREADY in_acc 1 1 } } }
	s_axis_q { axis {  { s_axis_q_TDATA in_data 0 128 }  { s_axis_q_TVALID in_vld 0 1 }  { s_axis_q_TREADY in_acc 1 1 } } }
	m_axis_i { axis {  { m_axis_i_TDATA out_data 1 128 }  { m_axis_i_TVALID out_vld 1 1 }  { m_axis_i_TREADY out_acc 0 1 } } }
	m_axis_q { axis {  { m_axis_q_TDATA out_data 1 128 }  { m_axis_q_TVALID out_vld 1 1 }  { m_axis_q_TREADY out_acc 0 1 } } }
	enable { ap_none {  { enable in_data 0 1 } } }
	reset_phase { ap_none {  { reset_phase in_data 0 1 } } }
	phase_offset { ap_none {  { phase_offset in_data 0 32 } } }
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
