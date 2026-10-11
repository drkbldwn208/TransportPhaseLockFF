# A6: reuse the existing HLS tone/demod IPs for a separate laser-loop analyzer.
# Requires this project's BD open; leaves the transport analyzer connected.
set fra_root [file normalize [file join [file dirname [info script]] ..]]
source $fra_root/scripts/refresh_laser_pll_sources.tcl
if {[get_property CONFIG.NUM_MI [get_bd_cells axi_interconnect_0]] < 28} {
    set_property CONFIG.NUM_MI 28 [get_bd_cells axi_interconnect_0]
}
foreach {name vlnv index address interface segment} {
    pll_fra        xilinx.com:ip:axi_gpio:2.0          23 0xA0250000 S_AXI Reg
    pll_fra_window xilinx.com:ip:axi_gpio:2.0          24 0xA0260000 S_AXI Reg
    pll_fra_tone   xilinx.com:hls:perturbation_gen:1.0 25 0xA0270000 s_axi_ctrl Reg
    pll_fra_error  xilinx.com:hls:demod_err:1.0        26 0xA0280000 s_axi_ctrl Reg
    pll_fra_drive  xilinx.com:hls:demod_err:1.0        27 0xA0290000 s_axi_ctrl Reg
} {
    if {![llength [get_bd_cells -quiet $name]]} {
        set cell [create_bd_cell -type ip -vlnv $vlnv $name]
        if {[string match *axi_gpio* $vlnv]} {
            set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_GPIO2_WIDTH {32} \
                CONFIG.C_ALL_OUTPUTS {1} CONFIG.C_ALL_INPUTS {0} CONFIG.C_DOUT_DEFAULT {0x00000000}] $cell
            set_property -dict [list CONFIG.C_ALL_OUTPUTS_2 [expr {$name eq "pll_fra_window"}] \
                CONFIG.C_ALL_INPUTS_2 [expr {$name ne "pll_fra_window"}] CONFIG.C_DOUT_DEFAULT_2 {0x00000000}] $cell
            set clock s_axi_aclk
            set reset s_axi_aresetn
        } else {set clock ap_clk; set reset ap_rst_n}
        set master [format "M%02d" $index]
        connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/${master}_AXI] [get_bd_intf_pins $name/$interface]
        foreach pin [list $name/$clock axi_interconnect_0/${master}_ACLK] {
            connect_bd_net [get_bd_pins usp_rf_data_converter_0/clk_adc1] [get_bd_pins $pin]
        }
        foreach pin [list $name/$reset axi_interconnect_0/${master}_ARESETN] {
            connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] [get_bd_pins $pin]
        }
        assign_bd_address -offset $address -range 64K -target_address_space \
            [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $name/$interface/$segment] -force
    }
}
foreach {gpio pin} {
    pll_fra/gpio_io_o fra_control
    pll_fra/gpio2_io_i fra_status
    pll_fra_window/gpio_io_o fra_settle_clocks
    pll_fra_window/gpio2_io_o fra_measure_clocks
} {
    if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins laser_pll_0/$pin]]]} {
        connect_bd_net [get_bd_pins $gpio] [get_bd_pins laser_pll_0/$pin]
    }
}
foreach {source sink} {
    pll_fra_tone/perturb_err_out laser_pll_0/s_fra_tone
    pll_fra_tone/ref_out laser_pll_0/s_fra_ref
    laser_pll_0/m_fra_error pll_fra_error/probe_in
    laser_pll_0/m_fra_error_ref pll_fra_error/ref_in
    laser_pll_0/m_fra_drive pll_fra_drive/probe_in
    laser_pll_0/m_fra_drive_ref pll_fra_drive/ref_in
} {
    if {![llength [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins $sink]]]} {
        connect_bd_intf_net [get_bd_intf_pins $source] [get_bd_intf_pins $sink]
    }
}
# Drain unused NCO perturbations: blocking this port would stall the HLS tone.
if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins pll_fra_tone/perturb_nco_out_TREADY]]]} {
    if {![llength [get_bd_cells -quiet pll_fra_one]]} {
        create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 pll_fra_one
        set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {1}] [get_bd_cells pll_fra_one]
    }
    connect_bd_net [get_bd_pins pll_fra_one/dout] [get_bd_pins pll_fra_tone/perturb_nco_out_TREADY]
}
validate_bd_design
save_bd_design
puts "A6 closed-loop analyzer integrated"
