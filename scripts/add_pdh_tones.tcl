# PDH2: direct real waveform on previously unused DAC230/0; reference DAC228/2.
# Keep converter settings of all previously active tiles and feedback paths.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[current_project -quiet] eq ""} {open_project $root/TransportPhaseLockFF.xpr}
open_bd_design [get_files design_1.bd]
foreach old [get_files -quiet *pdh_offset_*.mem] {remove_files $old}
foreach path [glob $root/TransportPhaseLockFF.srcs/sources_1/new/pdh*] {
    if {[string match *pdh_offset_*.mem $path]} {continue}
    if {![llength [get_files -quiet $path]]} {add_files -norecurse $path}
}
source $root/scripts/refresh_laser_pll_sources.tcl
foreach name {laser_pll_0 laser_pll_1} {
    set_property CONFIG.ENABLE_RF_SOURCE 0 [get_bd_cells $name]
}
set clk [get_bd_pins usp_rf_data_converter_0/clk_adc1]
set rst [get_bd_pins proc_sys_reset_0/peripheral_aresetn]
set rf [get_bd_cells usp_rf_data_converter_0]
# Tile229 already distributes the 491.52 MHz input reference. Tile230 uses it
# through the internal clock network, with its own PLL at the same 6.88128 GS/s.
set_property -dict [list CONFIG.DAC2_Enable 1 CONFIG.DAC2_PLL_Enable true \
    CONFIG.DAC2_Clock_Source 5 CONFIG.DAC2_Clock_Dist 0 \
    CONFIG.DAC2_Refclk_Freq 491.520 CONFIG.DAC2_Sampling_Rate 6.88128 \
    CONFIG.DAC2_Link_Coupling 1 CONFIG.DAC_Slice20_Enable true \
    CONFIG.DAC_Data_Type20 0 CONFIG.DAC_Data_Width20 14 \
    CONFIG.DAC_Interpolation_Mode20 2 CONFIG.DAC_Mixer_Type20 1 \
    CONFIG.DAC_Mixer_Mode20 2 CONFIG.DAC_Coarse_Mixer_Freq20 3 \
    CONFIG.DAC_Mode20 0] $rf
foreach {source sink} [list $clk usp_rf_data_converter_0/s2_axis_aclk $rst usp_rf_data_converter_0/s2_axis_aresetn] {
    set pin [get_bd_pins $sink]
    set net [get_bd_nets -quiet -of_objects $pin]
    if {[llength $net]} {disconnect_bd_net $net $pin}
    connect_bd_net $source $pin
}
if {![llength [get_bd_intf_ports -quiet vout20]]} {
    make_bd_intf_pins_external [get_bd_intf_pins usp_rf_data_converter_0/vout20]
    set net [get_bd_intf_nets -of_objects [get_bd_intf_pins usp_rf_data_converter_0/vout20]]
    set port [get_bd_intf_ports -of_objects $net]
    set_property name vout20 $port
}
if {![llength [get_bd_cells -quiet pdh_tones_0]]} {
    create_bd_cell -type module -reference pdh_tones_wrapper pdh_tones_0
    connect_bd_net $clk [get_bd_pins pdh_tones_0/clk]
    connect_bd_net $rst [get_bd_pins pdh_tones_0/rst_n]
} else {update_module_reference [get_ips design_1_pdh_tones_0_0]}
set_property CONFIG.NUM_MI 9 [get_bd_cells intensity_servo_axi]
foreach {name index address dual input1 input2} {
    pdh_control    06 0xA03C0000 1 0 1
    pdh_amplitudes 07 0xA03D0000 1 0 0
    pdh_version    08 0xA03E0000 0 1 0
} {
    if {![llength [get_bd_cells -quiet $name]]} {
        set g [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 $name]
        set_property -dict [list CONFIG.C_IS_DUAL $dual CONFIG.C_GPIO_WIDTH 32 CONFIG.C_GPIO2_WIDTH 32 \
            CONFIG.C_ALL_INPUTS $input1 CONFIG.C_ALL_OUTPUTS [expr {!$input1}] \
            CONFIG.C_ALL_INPUTS_2 $input2 CONFIG.C_ALL_OUTPUTS_2 [expr {!$input2}] \
            CONFIG.C_DOUT_DEFAULT 0x00000000 CONFIG.C_DOUT_DEFAULT_2 0x00000000] $g
        connect_bd_intf_net [get_bd_intf_pins intensity_servo_axi/M${index}_AXI] [get_bd_intf_pins $name/S_AXI]
        connect_bd_net $clk [get_bd_pins $name/s_axi_aclk] [get_bd_pins intensity_servo_axi/M${index}_ACLK]
        connect_bd_net $rst [get_bd_pins $name/s_axi_aresetn] [get_bd_pins intensity_servo_axi/M${index}_ARESETN]
        assign_bd_address -offset $address -range 64K -target_address_space \
            [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $name/S_AXI/Reg] -force
    }
}
foreach {source sink} {
    pdh_control/gpio_io_o pdh_tones_0/control
    pdh_tones_0/status pdh_control/gpio2_io_i
    pdh_amplitudes/gpio_io_o pdh_tones_0/amplitudes
    pdh_amplitudes/gpio2_io_o pdh_tones_0/reference_coefficients
    pdh_tones_0/feature_version pdh_version/gpio_io_i
} {
    set pin [get_bd_pins $sink]
    set net [get_bd_nets -quiet -of_objects $pin]
    if {[llength $net]} {disconnect_bd_net $net $pin}
    connect_bd_net [get_bd_pins $source] $pin
}
# Disconnect the former PDH stream before reconnecting the disabled (zero)
# RF-FRA source to DAC229/2. The DAC consumes data even when TVALID is low.
foreach interface {pdh_tones_0/m_sum laser_pll_0/m_rf_axis} {
    foreach net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins $interface]] {delete_bd_objs $net}
}
set pin [get_bd_pins laser_pll_0/m_rf_axis_tready]
foreach net [get_bd_nets -quiet -of_objects $pin] {disconnect_bd_net $net $pin}
foreach {source sink} {
    pdh_tones_0/m_sum usp_rf_data_converter_0/s20_axis
    pdh_tones_0/m_ref usp_rf_data_converter_0/s02_axis
    laser_pll_0/m_rf_axis usp_rf_data_converter_0/s12_axis
} {
    set pin [get_bd_intf_pins $sink]
    set net [get_bd_intf_nets -quiet -of_objects $pin]
    if {[llength $net]} {delete_bd_objs $net}
    connect_bd_intf_net [get_bd_intf_pins $source] $pin
}
validate_bd_design
save_bd_design
make_wrapper -files [get_files design_1.bd] -top
puts "PDH_BD_VALIDATED"
