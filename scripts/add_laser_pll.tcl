# Run in the existing Vivado project: source scripts/add_laser_pll.tcl
# The .bd is authoritative; root design_1.tcl predates the current project.
set pll_root [file normalize [file join [file dirname [info script]] ..]]
if {[current_project -quiet] eq ""} {
    open_project [file join $pll_root TransportPhaseLockFF.xpr]
}
open_bd_design [get_files design_1.bd]
if {[llength [get_bd_cells -quiet laser_pll_0]]} {
    error "laser_pll_0 already exists; this migration must only be applied once"
}
set pll_src [file join $pll_root TransportPhaseLockFF.srcs sources_1 new]
if {![file exists $pll_src/laser_pll_sine.mem]} {
    error "Missing laser_pll_sine.mem; run python3 scripts/generate_laser_pll_tables.py"
}
add_files -norecurse [glob $pll_src/laser_pll*.sv $pll_src/laser_pll*.v $pll_src/laser_pll*.vh $pll_src/laser_pll*.mem]
set_property include_dirs [list $pll_src] [get_filesets sources_1]
update_compile_order -fileset sources_1

# Replace the test receiver; preserve its downstream DMA/filter cells, now idle.
# Remove their AXI address segment before removing the derotator.
delete_bd_objs [get_bd_addr_segs -quiet zynq_ultra_ps_e_0/Data/SEG_rfdc_iq_derotator_4l_0_Reg]
delete_bd_objs [get_bd_cells {iq_split_1 rfdc_iq_derotator_4l_0 AxisConstant14Samples_1}]
# Disable the abandoned test filters explicitly; their downstream DMA stays idle.
foreach name {ssr4_fir_decimator_0 ssr4_fir_decimator_1} {
    connect_bd_net [get_bd_pins xlconstant_0/dout] [get_bd_pins $name/s_axis_TVALID]
}

set rfdc [get_bd_cells usp_rf_data_converter_0]
# ADC tile 224/block 3: real, 1x, eight 16-bit samples per fabric beat.
# ADC Mixer_Mode=2, Mixer_Type=1, Coarse_Mixer_Freq=3 are the GUI bypass encodings,
# NOT the xrfdc driver enums.
set_property -dict [list CONFIG.ADC_Data_Type03 {0} \
    CONFIG.ADC_Decimation_Mode03 {1} CONFIG.ADC_Data_Width03 {8} \
    CONFIG.ADC_Mixer_Type03 {1} CONFIG.ADC_Mixer_Mode03 {2} CONFIG.ADC_Coarse_Mixer_Freq03 {3} \
    CONFIG.ADC_NCO_Freq03 {0}] $rfdc
# Keep the DAC rate/packing used by its tile; the zero-frequency fine mixer
# converts seven (I=error,Q=0) pairs into a baseband analog error voltage.
set_property -dict [list CONFIG.DAC_NCO_Freq11 {0} CONFIG.DAC_NCO_Phase11 {0}] $rfdc
create_bd_cell -type module -reference laser_pll_wrapper laser_pll_0
connect_bd_intf_net [get_bd_intf_pins usp_rf_data_converter_0/m03_axis] [get_bd_intf_pins laser_pll_0/s_axis]
connect_bd_intf_net [get_bd_intf_pins laser_pll_0/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s11_axis]
connect_bd_net [get_bd_pins usp_rf_data_converter_0/clk_adc1] [get_bd_pins laser_pll_0/clk]
connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] [get_bd_pins laser_pll_0/rst_n]

# Reuse the removed test IP's M16 slot and add two slots. GPIOs live in the
# RF clock domain; the AXI interconnect performs the PS clock conversion.
set_property CONFIG.NUM_MI 19 [get_bd_cells axi_interconnect_0]
foreach {name index address input_only} {
    pll_frequency 16 0xA01E0000 0
    pll_control   17 0xA01F0000 0
    pll_status    18 0xA0200000 1
} {
    set gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 $name]
    set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_GPIO2_WIDTH {32} \
        CONFIG.C_ALL_INPUTS $input_only CONFIG.C_ALL_INPUTS_2 $input_only \
        CONFIG.C_ALL_OUTPUTS [expr {!$input_only}] CONFIG.C_ALL_OUTPUTS_2 [expr {!$input_only}]] $gpio
    set master [format "M%02d" $index]
    connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/${master}_AXI] [get_bd_intf_pins $name/S_AXI]
    connect_bd_net [get_bd_pins usp_rf_data_converter_0/clk_adc1] [get_bd_pins $name/s_axi_aclk]
    connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] [get_bd_pins $name/s_axi_aresetn]
    if {$index != 16} {
        connect_bd_net [get_bd_pins usp_rf_data_converter_0/clk_adc1] [get_bd_pins axi_interconnect_0/${master}_ACLK]
        connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] [get_bd_pins axi_interconnect_0/${master}_ARESETN]
    }
    assign_bd_address -offset $address -range 64K -target_address_space \
        [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $name/S_AXI/Reg] -force
}
foreach {gpio pin} {
    pll_frequency/gpio_io_o frequency_low
    pll_frequency/gpio2_io_o frequency_high
    pll_control/gpio_io_o control
    pll_control/gpio2_io_o phase_offset
    pll_status/gpio_io_i phase_status
    pll_status/gpio2_io_i frequency_status
} {
    connect_bd_net [get_bd_pins $gpio] [get_bd_pins laser_pll_0/$pin]
}
validate_bd_design
save_bd_design
puts "Laser PLL integrated. Rebuild bitstream and deploy matching bit/hwh together."
