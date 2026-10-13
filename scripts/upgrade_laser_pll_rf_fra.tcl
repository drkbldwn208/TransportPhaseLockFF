# R7 normal PLLs plus error-injection / RF phase-injection measurements.
# ADC/DAC rates and all normal PLL connections stay fixed. Project must be closed in GUI.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[current_project -quiet] eq ""} {open_project $root/TransportPhaseLockFF.xpr}
open_bd_design [get_files design_1.bd]
# Remove A8 diagnostic mean registers before refreshing the restored R7 interface.
foreach name {pll_loopback_i pll_loopback_q} {
    if {[llength [get_bd_cells -quiet $name]]} {delete_bd_objs [get_bd_cells $name]}
}
set_property CONFIG.NUM_MI 26 [get_bd_cells pll_extension_axi]
source $root/scripts/refresh_laser_pll_sources.tcl
if {![llength [get_bd_cells -quiet pll_rf_source]]} {
    set cell [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 pll_rf_source]
    set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_GPIO2_WIDTH {32} \
        CONFIG.C_ALL_OUTPUTS {1} CONFIG.C_ALL_INPUTS {0} CONFIG.C_DOUT_DEFAULT {0x00007FFF} \
        CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_ALL_OUTPUTS_2 {0}] $cell
    connect_bd_intf_net [get_bd_intf_pins pll_extension_axi/M25_AXI] [get_bd_intf_pins pll_rf_source/S_AXI]
    foreach pin {pll_rf_source/s_axi_aclk pll_extension_axi/M25_ACLK} {
        if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins $pin]]]} {
            connect_bd_net [get_bd_pins usp_rf_data_converter_0/clk_adc1] [get_bd_pins $pin]
        }
    }
    foreach pin {pll_rf_source/s_axi_aresetn pll_extension_axi/M25_ARESETN} {
        if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins $pin]]]} {
            connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] [get_bd_pins $pin]
        }
    }
    assign_bd_address -offset 0xA0300000 -range 64K -target_address_space \
        [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs pll_rf_source/S_AXI/Reg] -force
}
foreach {source sink} {
    pll_rf_source/gpio_io_o laser_pll_0/rf_source_control
    pll_rf_source/gpio_io_o laser_pll_1/rf_source_control
    laser_pll_0/rf_source_status pll_rf_source/gpio2_io_i
    pll_fra_one/dout laser_pll_1/m_rf_axis_tready
} {
    if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins $sink]]]} {
        connect_bd_net [get_bd_pins $source] [get_bd_pins $sink]
    }
}
# The old broadcaster fed the identical I=32767,Q=0 carrier into DAC229/0 and /2.
# Keep /0 constant, and independently phase-modulate only /2.
if {[llength [get_bd_cells -quiet axis_broadcaster_0]]} {delete_bd_objs [get_bd_cells axis_broadcaster_0]}
foreach {source sink} {
    AxisConstant14Samples_0/m_axis usp_rf_data_converter_0/s10_axis
    laser_pll_0/m_rf_axis usp_rf_data_converter_0/s12_axis
} {
    set net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins $sink]]
    if {[llength $net]} {disconnect_bd_intf_net $net [get_bd_intf_pins $sink]}
    connect_bd_intf_net [get_bd_intf_pins $source] [get_bd_intf_pins $sink]
}
validate_bd_design
save_bd_design
puts "R7_RF_FRA_BD_VALIDATED"
