# IS03: opt-in calibrated controller and independent shot monitor. Legacy HLS,
# RFDC mixers, both PLLs, and the existing intensity FRA remain connected.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[current_project -quiet] eq ""} {open_project $root/TransportPhaseLockFF.xpr}
open_bd_design [get_files design_1.bd]
foreach name {intensity_compensator.sv intensity_linearized.sv intensity_linearized_wrapper.v intensity_shot_capture.sv intensity_shot_capture_wrapper.v} {
    set path $root/TransportPhaseLockFF.srcs/sources_1/new/$name
    if {![llength [get_files -quiet $path]]} {add_files -norecurse $path}
}
update_compile_order -fileset sources_1
proc is_link {source sink} {
    set pin [get_bd_pins $sink]
    set net [get_bd_nets -quiet -of_objects $pin]
    if {[llength $net]} {disconnect_bd_net $net $pin}
    connect_bd_net [get_bd_pins $source] $pin
}
set clk [get_bd_pins usp_rf_data_converter_0/clk_adc1]
set rst [get_bd_pins proc_sys_reset_0/peripheral_aresetn]
foreach {cell reference} {
    intensity_linearized_0 intensity_linearized_wrapper
    intensity_shot_capture_0 intensity_shot_capture_wrapper
} {
    if {![llength [get_bd_cells -quiet $cell]]} {
        create_bd_cell -type module -reference $reference $cell
        connect_bd_net $clk [get_bd_pins $cell/clk]
        connect_bd_net $rst [get_bd_pins $cell/rst_n]
    } else {update_module_reference [get_ips design_1_${cell}_0]}
}
# The existing AXI interconnect has only one master slot left. A small secondary
# interconnect provides the six slow control ports without altering old addresses.
if {![llength [get_bd_cells -quiet intensity_servo_axi]]} {
    set_property CONFIG.NUM_MI 32 [get_bd_cells pll_extension_axi]
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 intensity_servo_axi
    set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 6] [get_bd_cells intensity_servo_axi]
    connect_bd_intf_net [get_bd_intf_pins pll_extension_axi/M31_AXI] [get_bd_intf_pins intensity_servo_axi/S00_AXI]
    connect_bd_net $clk [get_bd_pins pll_extension_axi/M31_ACLK] [get_bd_pins intensity_servo_axi/ACLK] [get_bd_pins intensity_servo_axi/S00_ACLK]
    connect_bd_net $rst [get_bd_pins pll_extension_axi/M31_ARESETN] [get_bd_pins intensity_servo_axi/ARESETN] [get_bd_pins intensity_servo_axi/S00_ARESETN]
}
foreach {name index address d1 d2} {
    intensity_servo_control 00 0xA0360000 0 1
    intensity_servo_write   01 0xA0370000 0 0
    intensity_servo_read    02 0xA0380000 1 1
    intensity_shot_control 03 0xA0390000 0 1
    intensity_shot_tail    04 0xA03A0000 0 1
} {
    if {![llength [get_bd_cells -quiet $name]]} {
        set g [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 $name]
        set_property -dict [list CONFIG.C_IS_DUAL 1 CONFIG.C_GPIO_WIDTH 32 CONFIG.C_GPIO2_WIDTH 32 \
            CONFIG.C_ALL_INPUTS $d1 CONFIG.C_ALL_OUTPUTS [expr {!$d1}] \
            CONFIG.C_ALL_INPUTS_2 $d2 CONFIG.C_ALL_OUTPUTS_2 [expr {!$d2}] \
            CONFIG.C_DOUT_DEFAULT 0x00000000 CONFIG.C_DOUT_DEFAULT_2 0x00000000] $g
        connect_bd_intf_net [get_bd_intf_pins intensity_servo_axi/M${index}_AXI] [get_bd_intf_pins $name/S_AXI]
        connect_bd_net $clk [get_bd_pins $name/s_axi_aclk] [get_bd_pins intensity_servo_axi/M${index}_ACLK]
        connect_bd_net $rst [get_bd_pins $name/s_axi_aresetn] [get_bd_pins intensity_servo_axi/M${index}_ARESETN]
        assign_bd_address -offset $address -range 64K -target_address_space \
            [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $name/S_AXI/Reg] -force
    }
}
foreach {source sink} {
    intensity_rx_lowpass_0/filtered_i intensity_linearized_0/adc_bus
    intensity_rx_lowpass_0/filtered_valid intensity_linearized_0/adc_valid
    setpoint_switch_0/setpoint_out intensity_linearized_0/reference_in
    fast_servo_controller_0/dac_out intensity_linearized_0/legacy_command
    dwell_fcw_streamer_32_0/active_r intensity_linearized_0/shot_active
    intensity_linearized_0/command_out intensity_probe_0/controller_command
    intensity_servo_control/gpio_io_o intensity_linearized_0/control
    intensity_linearized_0/status intensity_servo_control/gpio2_io_i
    intensity_servo_write/gpio_io_o intensity_linearized_0/write_address
    intensity_servo_write/gpio2_io_o intensity_linearized_0/write_data
    intensity_linearized_0/read_data intensity_servo_read/gpio_io_i
    intensity_linearized_0/feature_version intensity_servo_read/gpio2_io_i
    dwell_fcw_streamer_32_0/active_r intensity_shot_capture_0/shot_active
    intensity_rx_lowpass_0/filtered_valid intensity_shot_capture_0/sample_valid
    intensity_linearized_0/error_q8 intensity_shot_capture_0/error_q8
    intensity_linearized_0/reference_power intensity_shot_capture_0/reference_power
    intensity_linearized_0/measured_power intensity_shot_capture_0/measured_power
    intensity_probe_0/command_out intensity_shot_capture_0/actuator_codes
    intensity_linearized_0/raw_adc intensity_shot_capture_0/raw_adc
    intensity_linearized_0/sample_flags intensity_shot_capture_0/sample_flags
    intensity_shot_control/gpio_io_o intensity_shot_capture_0/control
    intensity_shot_capture_0/status intensity_shot_control/gpio2_io_i
    intensity_shot_tail/gpio_io_o intensity_shot_capture_0/tail_clocks
    intensity_shot_capture_0/feature_version intensity_shot_tail/gpio2_io_i
} {is_link $source $sink}
if {![llength [get_bd_cells -quiet intensity_shot_dma]]} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 intensity_shot_dma
    set_property -dict [list CONFIG.c_addr_width 50 CONFIG.c_include_mm2s 0 CONFIG.c_include_sg 0 \
        CONFIG.c_m_axi_s2mm_data_width 128 CONFIG.c_s_axis_s2mm_tdata_width 128 CONFIG.c_sg_length_width 26] [get_bd_cells intensity_shot_dma]
    connect_bd_intf_net [get_bd_intf_pins intensity_servo_axi/M05_AXI] [get_bd_intf_pins intensity_shot_dma/S_AXI_LITE]
    connect_bd_net $clk [get_bd_pins intensity_shot_dma/s_axi_lite_aclk] [get_bd_pins intensity_shot_dma/m_axi_s2mm_aclk] [get_bd_pins intensity_servo_axi/M05_ACLK]
    connect_bd_net $rst [get_bd_pins intensity_shot_dma/axi_resetn] [get_bd_pins intensity_servo_axi/M05_ARESETN]
    assign_bd_address -offset 0xA03B0000 -range 64K -target_address_space \
        [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs intensity_shot_dma/S_AXI_LITE/Reg] -force
    set_property CONFIG.NUM_SI 11 [get_bd_cells smartconnect_0]
    connect_bd_intf_net [get_bd_intf_pins intensity_shot_dma/M_AXI_S2MM] [get_bd_intf_pins smartconnect_0/S10_AXI]
    assign_bd_address -target_address_space [get_bd_addr_spaces intensity_shot_dma/Data_S2MM]
    create_bd_cell -type ip -vlnv xilinx.com:ip:axis_data_fifo:2.0 intensity_shot_fifo
    set_property -dict [list CONFIG.TDATA_NUM_BYTES 16 CONFIG.FIFO_DEPTH 1024 CONFIG.HAS_TLAST 1 CONFIG.IS_ACLK_ASYNC 0] [get_bd_cells intensity_shot_fifo]
    connect_bd_net $clk [get_bd_pins intensity_shot_fifo/s_axis_aclk]
    connect_bd_net [get_bd_pins intensity_shot_capture_0/fifo_rst_n] [get_bd_pins intensity_shot_fifo/s_axis_aresetn]
    connect_bd_intf_net [get_bd_intf_pins intensity_shot_capture_0/m_axis] [get_bd_intf_pins intensity_shot_fifo/S_AXIS]
    connect_bd_intf_net [get_bd_intf_pins intensity_shot_fifo/M_AXIS] [get_bd_intf_pins intensity_shot_dma/S_AXIS_S2MM]
}
# Repair the known INT2 sink-only ILA nets in the actual hardware and HWH.
foreach {source sink} {
    cordic_0/m_axis_dout_tdata system_ila_0/SLOT_0_AXIS_tdata
    cordic_0/m_axis_dout_tvalid system_ila_0/SLOT_0_AXIS_tvalid
    cordic_0/m_axis_dout_tdata system_ila_0/SLOT_5_AXIS_tdata
    cordic_0/m_axis_dout_tvalid system_ila_0/SLOT_5_AXIS_tvalid
    cordic_average_0/m_axis_cartesian_tdata system_ila_0/SLOT_1_AXIS_tdata
    cordic_average_0/m_axis_cartesian_tvalid system_ila_0/SLOT_1_AXIS_tvalid
} {is_link $source $sink}
validate_bd_design
save_bd_design
make_wrapper -files [get_files design_1.bd] -top
puts "INTENSITY_LINEARIZED_BD_VALIDATED"
