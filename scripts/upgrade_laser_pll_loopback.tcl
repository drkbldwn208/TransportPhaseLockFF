# A8 post-DDC/FIR diagnostic I/Q readout. No RFDC configuration or existing stream connections change.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[current_project -quiet] eq ""} {open_project $root/TransportPhaseLockFF.xpr}
open_bd_design [get_files design_1.bd]
source $root/scripts/refresh_laser_pll_sources.tcl
set_property CONFIG.NUM_MI 27 [get_bd_cells pll_extension_axi]
foreach {name index address low high} {
    pll_loopback_i 25 0xA0300000 loopback_i_low loopback_i_high
    pll_loopback_q 26 0xA0310000 loopback_q_low loopback_q_high
} {
    if {![llength [get_bd_cells -quiet $name]]} {
        set cell [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 $name]
        set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_GPIO2_WIDTH {32} \
            CONFIG.C_ALL_INPUTS {1} CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_ALL_OUTPUTS {0} CONFIG.C_ALL_OUTPUTS_2 {0}] $cell
        set master [format M%02d $index]
        connect_bd_intf_net [get_bd_intf_pins pll_extension_axi/${master}_AXI] [get_bd_intf_pins $name/S_AXI]
        foreach pin [list $name/s_axi_aclk pll_extension_axi/${master}_ACLK] {
            connect_bd_net [get_bd_pins usp_rf_data_converter_0/clk_adc1] [get_bd_pins $pin]
        }
        foreach pin [list $name/s_axi_aresetn pll_extension_axi/${master}_ARESETN] {
            connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] [get_bd_pins $pin]
        }
        connect_bd_net [get_bd_pins laser_pll_0/$low] [get_bd_pins $name/gpio_io_i]
        connect_bd_net [get_bd_pins laser_pll_0/$high] [get_bd_pins $name/gpio2_io_i]
        assign_bd_address -offset $address -range 64K -target_address_space \
            [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $name/S_AXI/Reg] -force
    }
}
validate_bd_design
save_bd_design
