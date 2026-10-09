# A5: fourth detector stage + independent I/Q snapshots on the idle axi_dma_3.
# Requires the project/BD open. Existing analog and ILA connections are preserved
# except the old idle IQ packetizer's connection to this same DMA.
set tracking_root [file normalize [file join [file dirname [info script]] ..]]
source $tracking_root/scripts/refresh_laser_pll_sources.tcl
if {[get_property CONFIG.NUM_MI [get_bd_cells axi_interconnect_0]] < 23} {
    set_property CONFIG.NUM_MI 23 [get_bd_cells axi_interconnect_0]
}
foreach {name index address default_value} {
    pll_tracking 21 0xA0230000 0x000000E0
    pll_monitor  22 0xA0240000 0x00000000
} {
    if {![llength [get_bd_cells -quiet $name]]} {
        set gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 $name]
        set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_GPIO2_WIDTH {32} \
            CONFIG.C_ALL_INPUTS {0} CONFIG.C_ALL_OUTPUTS {1} \
            CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_ALL_OUTPUTS_2 {0} CONFIG.C_DOUT_DEFAULT $default_value] $gpio
        set master [format "M%02d" $index]
        connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/${master}_AXI] [get_bd_intf_pins $name/S_AXI]
        foreach pin [list $name/s_axi_aclk axi_interconnect_0/${master}_ACLK] {
            connect_bd_net [get_bd_pins usp_rf_data_converter_0/clk_adc1] [get_bd_pins $pin]
        }
        foreach pin [list $name/s_axi_aresetn axi_interconnect_0/${master}_ARESETN] {
            connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] [get_bd_pins $pin]
        }
        assign_bd_address -offset $address -range 64K -target_address_space \
            [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $name/S_AXI/Reg] -force
    }
}
foreach {gpio pin} {
    pll_tracking/gpio_io_o tracking_control
    pll_tracking/gpio2_io_i tracking_status
    pll_monitor/gpio_io_o monitor_control
    pll_monitor/gpio2_io_i monitor_status
} {
    if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins laser_pll_0/$pin]]]} {
        connect_bd_net [get_bd_pins $gpio] [get_bd_pins laser_pll_0/$pin]
    }
}
if {![llength [get_bd_cells -quiet pll_iq_fifo]]} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:axis_data_fifo:2.0 pll_iq_fifo
    set_property -dict [list CONFIG.TDATA_NUM_BYTES {16} CONFIG.FIFO_DEPTH {1024} \
        CONFIG.HAS_TLAST {1} CONFIG.IS_ACLK_ASYNC {0}] [get_bd_cells pll_iq_fifo]
    connect_bd_net [get_bd_pins usp_rf_data_converter_0/clk_adc1] [get_bd_pins pll_iq_fifo/s_axis_aclk]
    connect_bd_net [get_bd_pins laser_pll_0/monitor_fifo_rst_n] [get_bd_pins pll_iq_fifo/s_axis_aresetn]
    # The old FIFO/decimators have been idle since ADC 224/3 was reassigned.
    # Detach both interface and explicit ready/last nets from the old packetizer.
    set old_intf [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins axi_dma_3/S_AXIS_S2MM]]
    if {[llength $old_intf]} {delete_bd_objs $old_intf}
    foreach pin {axis_tlast_gen_iq_0/m_axis_tready axis_tlast_gen_iq_0/m_axis_tlast} {
        set net [get_bd_nets -quiet -of_objects [get_bd_pins $pin]]
        if {[llength $net]} {disconnect_bd_net $net [get_bd_pins $pin]}
    }
    connect_bd_net [get_bd_pins xlconstant_0/dout] [get_bd_pins axis_tlast_gen_iq_0/m_axis_tready]
    connect_bd_intf_net [get_bd_intf_pins laser_pll_0/m_monitor] [get_bd_intf_pins pll_iq_fifo/S_AXIS]
    connect_bd_intf_net [get_bd_intf_pins pll_iq_fifo/M_AXIS] [get_bd_intf_pins axi_dma_3/S_AXIS_S2MM]
}
# Scalar probe nets override matching AXIS signals in Vivado. Reconnect all
# endpoints explicitly, including the DMA pins, not just the FIFO and ILA.
foreach {fifo_pin dma_pin probe} {
    m_axis_tready s_axis_s2mm_tready probe1
    m_axis_tlast  s_axis_s2mm_tlast  probe2
} {
    set pins [list pll_iq_fifo/$fifo_pin axi_dma_3/$dma_pin system_ila_0/$probe]
    foreach pin $pins {
        set net [get_bd_nets -quiet -of_objects [get_bd_pins $pin]]
        if {[llength $net]} {disconnect_bd_net $net [get_bd_pins $pin]}
    }
    connect_bd_net [get_bd_pins pll_iq_fifo/$fifo_pin] [get_bd_pins axi_dma_3/$dma_pin] \
        [get_bd_pins system_ila_0/$probe]
}
puts "A5 tracking and nonblocking IQ monitor integrated"
