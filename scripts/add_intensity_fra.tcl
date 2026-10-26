# Add a nonblocking, sample-resolved intensity diagnostic. RFDC and PI unchanged.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[current_project -quiet] eq ""} {open_project $root/TransportPhaseLockFF.xpr}
open_bd_design [get_files design_1.bd]
foreach file [glob $root/TransportPhaseLockFF.srcs/sources_1/new/intensity_*] {
    if {![llength [get_files -quiet $file]]} {add_files -norecurse $file}
}
update_compile_order -fileset sources_1
set clk [get_bd_pins usp_rf_data_converter_0/clk_adc1]
set rst [get_bd_pins proc_sys_reset_0/peripheral_aresetn]
proc intensity_link {source sink} {
    set net [get_bd_nets -quiet -of_objects [get_bd_pins $sink]]
    if {[llength $net]} {disconnect_bd_net $net [get_bd_pins $sink]}
    connect_bd_net [get_bd_pins $source] [get_bd_pins $sink]
}
if {![llength [get_bd_cells -quiet intensity_probe_0]]} {
    create_bd_cell -type module -reference intensity_probe_wrapper intensity_probe_0
} else {update_module_reference [get_ips design_1_intensity_probe_0_0]}
if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins intensity_probe_0/clk]]]} {
    connect_bd_net $clk [get_bd_pins intensity_probe_0/clk]
}
if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins intensity_probe_0/rst_n]]]} {
    connect_bd_net $rst [get_bd_pins intensity_probe_0/rst_n]
}
set_property CONFIG.NUM_MI 31 [get_bd_cells pll_extension_axi]
foreach {name index address d1 d2 default1} {
    intensity_control 26 0xA0310000 0 1 0x00000000
    intensity_tone    27 0xA0320000 0 0 0x00000000
    intensity_limits  28 0xA0330000 0 1 0x7FFF0000
    intensity_counts  29 0xA0340000 1 1 0x00000000
} {
    if {![llength [get_bd_cells -quiet $name]]} {
        set g [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 $name]
        set_property -dict [list CONFIG.C_IS_DUAL 1 CONFIG.C_GPIO_WIDTH 32 CONFIG.C_GPIO2_WIDTH 32 \
            CONFIG.C_ALL_INPUTS $d1 CONFIG.C_ALL_OUTPUTS [expr {!$d1}] \
            CONFIG.C_ALL_INPUTS_2 $d2 CONFIG.C_ALL_OUTPUTS_2 [expr {!$d2}] \
            CONFIG.C_DOUT_DEFAULT $default1 CONFIG.C_DOUT_DEFAULT_2 0x00000000] $g
        connect_bd_intf_net [get_bd_intf_pins pll_extension_axi/M${index}_AXI] [get_bd_intf_pins $name/S_AXI]
        connect_bd_net $clk [get_bd_pins $name/s_axi_aclk] [get_bd_pins pll_extension_axi/M${index}_ACLK]
        connect_bd_net $rst [get_bd_pins $name/s_axi_aresetn] [get_bd_pins pll_extension_axi/M${index}_ARESETN]
        assign_bd_address -offset $address -range 64K -target_address_space \
            [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $name/S_AXI/Reg] -force
    }
}
foreach {source sink} {
    iq_split_0/adc_bus intensity_probe_0/adc_bus
    iq_split_0/m_axis_i_tvalid intensity_probe_0/adc_valid
    pll_fra_one/dout intensity_probe_0/dac_ready
    fast_servo_controller_0/dac_out intensity_probe_0/controller_command
    axi_gpio_9/gpio_io_o intensity_probe_0/manual_enable
    axi_gpio_9/gpio2_io_o intensity_probe_0/manual_command
    intensity_probe_0/command_out sync_axis_power_mod_0/sync_in
    xlconstant_2/dout sync_axis_power_mod_0/open_loop_toggle
    intensity_control/gpio_io_o intensity_probe_0/control
    intensity_probe_0/status intensity_control/gpio2_io_i
    intensity_tone/gpio_io_o intensity_probe_0/frequency_word
    intensity_tone/gpio2_io_o intensity_probe_0/amplitude_word
    intensity_limits/gpio_io_o intensity_probe_0/limits
    intensity_probe_0/feature_version intensity_limits/gpio2_io_i
    intensity_probe_0/clip_samples intensity_counts/gpio_io_i
    intensity_probe_0/invalid_samples intensity_counts/gpio2_io_i
} {intensity_link $source $sink}
if {![llength [get_bd_cells -quiet intensity_dma]]} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 intensity_dma
    set_property -dict [list CONFIG.c_addr_width 50 CONFIG.c_include_mm2s 0 CONFIG.c_include_sg 0 \
        CONFIG.c_m_axi_s2mm_data_width 128 CONFIG.c_s_axis_s2mm_tdata_width 128 CONFIG.c_sg_length_width 26] [get_bd_cells intensity_dma]
    connect_bd_intf_net [get_bd_intf_pins pll_extension_axi/M30_AXI] [get_bd_intf_pins intensity_dma/S_AXI_LITE]
    connect_bd_net $clk [get_bd_pins intensity_dma/s_axi_lite_aclk] [get_bd_pins intensity_dma/m_axi_s2mm_aclk] [get_bd_pins pll_extension_axi/M30_ACLK]
    connect_bd_net $rst [get_bd_pins intensity_dma/axi_resetn] [get_bd_pins pll_extension_axi/M30_ARESETN]
    assign_bd_address -offset 0xA0350000 -range 64K -target_address_space \
        [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs intensity_dma/S_AXI_LITE/Reg] -force
    set_property CONFIG.NUM_SI 10 [get_bd_cells smartconnect_0]
    connect_bd_intf_net [get_bd_intf_pins intensity_dma/M_AXI_S2MM] [get_bd_intf_pins smartconnect_0/S09_AXI]
    assign_bd_address -target_address_space [get_bd_addr_spaces intensity_dma/Data_S2MM]
    create_bd_cell -type ip -vlnv xilinx.com:ip:axis_data_fifo:2.0 intensity_fifo
    set_property -dict [list CONFIG.TDATA_NUM_BYTES 16 CONFIG.FIFO_DEPTH 1024 CONFIG.HAS_TLAST 1 CONFIG.IS_ACLK_ASYNC 0] [get_bd_cells intensity_fifo]
    connect_bd_net $clk [get_bd_pins intensity_fifo/s_axis_aclk]
    connect_bd_net [get_bd_pins intensity_probe_0/fifo_rst_n] [get_bd_pins intensity_fifo/s_axis_aresetn]
    connect_bd_intf_net [get_bd_intf_pins intensity_probe_0/m_axis] [get_bd_intf_pins intensity_fifo/S_AXIS]
    connect_bd_intf_net [get_bd_intf_pins intensity_fifo/M_AXIS] [get_bd_intf_pins intensity_dma/S_AXIS_S2MM]
}
validate_bd_design
save_bd_design
make_wrapper -files [get_files design_1.bd] -top
puts "INTENSITY_FRA_BD_VALIDATED"
