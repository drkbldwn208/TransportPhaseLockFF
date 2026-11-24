# Extend the CURRENT saved BD; preserve converter and feedback settings.
set root [file normalize [file join [file dirname [info script]] ..]]
open_bd_design [get_files design_1.bd]
set src $root/TransportPhaseLockFF.srcs/sources_1/new
foreach name {gpio_word_cdc.v pdh_phase_accumulator.sv pdh_cosine_pair.sv pdh_quarter_cos.mem pdh_tones.sv pdh_tones_wrapper.v hist_counter.v pmod_edge_detect.v} {
    if {![llength [get_files -quiet $src/$name]]} {add_files -norecurse $src/$name}
}
# Retain old waveform files on disk, but they no longer belong in this build.
foreach old [concat [get_files -quiet *pdh_sum_*.mem] [get_files -quiet *pdh_reference_*.mem]] {remove_files $old}
update_compile_order -fileset sources_1
foreach name {design_1_pdh_tones_0_0 design_1_hist_counter_0_0 design_1_pmod_sync_edge_0_0} {
    update_module_reference [get_ips $name]
}
set clk [get_bd_pins usp_rf_data_converter_0/clk_adc1]
set rst [get_bd_pins proc_sys_reset_0/peripheral_aresetn]
connect_bd_net $clk [get_bd_pins pdh_tones_0/gpio_clk]
connect_bd_net [get_bd_pins pdh_amplitudes/gpio2_io_o] [get_bd_pins pdh_tones_0/reference_settings]
set_property CONFIG.NUM_MI 11 [get_bd_cells intensity_servo_axi]
foreach {name slot address low high} {
    pdh_carrier_frequency    09 0xA0400000 0 0
    pdh_modulation_frequency 10 0xA0410000 0 0
} {
    if {![llength [get_bd_cells -quiet $name]]} {
        set g [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 $name]
        set fcw [expr {$name eq "pdh_carrier_frequency" ? 98170681051429 : 4908534052571}]
        set_property -dict [list CONFIG.C_IS_DUAL 1 CONFIG.C_GPIO_WIDTH 32 CONFIG.C_GPIO2_WIDTH 32 \
            CONFIG.C_ALL_OUTPUTS 1 CONFIG.C_ALL_OUTPUTS_2 1 \
            CONFIG.C_DOUT_DEFAULT [format 0x%08X [expr {$fcw & 0xffffffff}]] \
            CONFIG.C_DOUT_DEFAULT_2 [format 0x%08X [expr {$fcw >> 32}]]] $g
        connect_bd_intf_net [get_bd_intf_pins intensity_servo_axi/M${slot}_AXI] [get_bd_intf_pins $name/S_AXI]
        connect_bd_net $clk [get_bd_pins $name/s_axi_aclk] [get_bd_pins intensity_servo_axi/M${slot}_ACLK]
        connect_bd_net $rst [get_bd_pins $name/s_axi_aresetn] [get_bd_pins intensity_servo_axi/M${slot}_ARESETN]
        assign_bd_address -offset $address -range 64K -target_address_space \
            [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $name/S_AXI/Reg] -force
    }
}
foreach {name prefix} {pdh_carrier_frequency carrier pdh_modulation_frequency modulation} {
    connect_bd_net [get_bd_pins $name/gpio_io_o] [get_bd_pins pdh_tones_0/${prefix}_fcw_low]
    connect_bd_net [get_bd_pins $name/gpio2_io_o] [get_bd_pins pdh_tones_0/${prefix}_fcw_high]
}
# The new histogram's GPIO lives on the PS clock, independently of the counter.
connect_bd_net [get_bd_pins photon_counting/axi_gpio_0/s_axi_aclk] [get_bd_pins photon_counting/hist_counter_0/gpio_clk]
connect_bd_net [get_bd_pins xlconstant_2/dout] [get_bd_pins photon_counting/pmod_debounce_sync_2/clear_latch]
# Mark the 2-flop input synchronizers, not a delay constraint on an async pin.
# Add the missing DMA-to-DDR path to the existing shared memory interconnect.
current_bd_instance /photon_counting
if {![llength [get_bd_intf_pins -quiet M_AXI]]} {
    create_bd_intf_pin -mode Master -vlnv xilinx.com:interface:aximm_rtl:1.0 M_AXI
    connect_bd_intf_net [get_bd_intf_pins axi_dma_3/M_AXI_S2MM] [get_bd_intf_pins M_AXI]
}
current_bd_instance /
set_property CONFIG.NUM_SI 10 [get_bd_cells smartconnect_0]
connect_bd_intf_net [get_bd_intf_pins photon_counting/M_AXI] [get_bd_intf_pins smartconnect_0/S09_AXI]
# Clock/reset for the second new AXI-lite slot was absent in the saved BD.
connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] [get_bd_pins pll_extension_axi/M19_ACLK]
connect_bd_net [get_bd_pins rst_ps8_0_99M/peripheral_aresetn] [get_bd_pins pll_extension_axi/M19_ARESETN]
# Keep the photon peripherals alongside the second PLL, outside the older
# interconnect's low-address windows. Automatic hole filling can make the
# hierarchical crossbar decode ranges overlap even when leaf addresses differ.
foreach {segment address} {
    photon_counting/axi_dma_3/S_AXI_LITE/Reg 0xA1130000
    photon_counting/axi_gpio_0/S_AXI/Reg 0xA1140000
} {
    assign_bd_address -offset $address -range 64K -target_address_space \
        [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $segment] -force
}
assign_bd_address -offset 0 -range 2G -target_address_space \
    [get_bd_addr_spaces photon_counting/axi_dma_3/Data_S2MM] \
    [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP2/HP0_DDR_LOW] -force
assign_bd_address -offset 0x800000000 -range 32G -target_address_space \
    [get_bd_addr_spaces photon_counting/axi_dma_3/Data_S2MM] \
    [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP2/HP0_DDR_HIGH] -force
validate_bd_design
save_bd_design
make_wrapper -files [get_files design_1.bd] -top
puts "PDH_TUNABLE_PHOTON_BD_VALIDATED"
