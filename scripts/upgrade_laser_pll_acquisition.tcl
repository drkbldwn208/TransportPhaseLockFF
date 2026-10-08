# Idempotent update of the existing laser_pll_0 block and its GPIOs.
set upgrade_root [file normalize [file join [file dirname [info script]] ..]]
source $upgrade_root/scripts/create_laser_pll_fft.tcl
source $upgrade_root/scripts/refresh_laser_pll_sources.tcl
# GUI enums: Nyquist 0=zone 1; calibration 2=AutoCal. PYNQ enums differ.
# The 200..950 MHz search band is entirely inside the first Nyquist zone.
set_property -dict [list CONFIG.ADC_Nyquist03 {0} CONFIG.ADC_CalOpt_Mode03 {2}] \
    [get_bd_cells usp_rf_data_converter_0]
set_property CONFIG.NUM_MI 21 [get_bd_cells axi_interconnect_0]
foreach {name index address input_only} {
    pll_acquisition        19 0xA0210000 0
    pll_acquisition_status 20 0xA0220000 1
} {
    if {![llength [get_bd_cells -quiet $name]]} {
        set gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 $name]
        set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_GPIO2_WIDTH {32} \
            CONFIG.C_ALL_INPUTS $input_only CONFIG.C_ALL_INPUTS_2 $input_only \
            CONFIG.C_ALL_OUTPUTS [expr {!$input_only}] CONFIG.C_ALL_OUTPUTS_2 [expr {!$input_only}]] $gpio
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
    pll_acquisition/gpio_io_o acquisition_control
    pll_acquisition/gpio2_io_o test_dc
    pll_acquisition_status/gpio_io_i acquisition_status
    pll_acquisition_status/gpio2_io_i fft_status
} {
    if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins laser_pll_0/$pin]]]} {
        connect_bd_net [get_bd_pins $gpio] [get_bd_pins laser_pll_0/$pin]
    }
}
# Reset remains muted; bit 2 selects the requested reversed default polarity.
set_property CONFIG.C_DOUT_DEFAULT {0x00000004} [get_bd_cells pll_control]
set_property CONFIG.C_DOUT_DEFAULT {0x00200041} [get_bd_cells pll_acquisition]
