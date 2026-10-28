# INT2: unity-gain image rejection before the existing PI and diagnostic.
# Calibration uses the existing slow rate, but averages I/Q before atan2.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[current_project -quiet] eq ""} {open_project $root/TransportPhaseLockFF.xpr}
open_bd_design [get_files design_1.bd]
foreach file [glob $root/TransportPhaseLockFF.srcs/sources_1/new/intensity_rx_*] {
    if {![llength [get_files -quiet $file]]} {add_files -norecurse $file}
}
update_compile_order -fileset sources_1
update_module_reference [get_ips design_1_intensity_probe_0_0]
proc rx_link {source sink} {
    set pin [get_bd_pins $sink]
    set net [get_bd_nets -quiet -of_objects $pin]
    if {[llength $net]} {disconnect_bd_net $net $pin}
    connect_bd_net [get_bd_pins $source] $pin
}
set clk [get_bd_pins usp_rf_data_converter_0/clk_adc1]
set rst [get_bd_pins proc_sys_reset_0/peripheral_aresetn]
if {![llength [get_bd_cells -quiet intensity_rx_lowpass_0]]} {
    create_bd_cell -type module -reference intensity_rx_lowpass_wrapper intensity_rx_lowpass_0
    connect_bd_net $clk [get_bd_pins intensity_rx_lowpass_0/clk]
    connect_bd_net $rst [get_bd_pins intensity_rx_lowpass_0/rst_n]
}
# Remove the legacy direct-I/Q interface sinks; new scalar wiring is explicit.
foreach pin {cordic_average_0/s_axis_i cordic_average_0/s_axis_q} {
    set net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins $pin]]
    if {[llength $net]} {disconnect_bd_intf_net $net [get_bd_intf_pins $pin]}
}
foreach {source sink} {
    iq_split_0/m_axis_i_tdata intensity_rx_lowpass_0/i_data
    iq_split_0/m_axis_q_tdata intensity_rx_lowpass_0/q_data
    iq_split_0/m_axis_i_tvalid intensity_rx_lowpass_0/sample_valid
    intensity_rx_lowpass_0/filtered_i fast_servo_controller_0/adc_bus
    intensity_rx_lowpass_0/filtered_i intensity_probe_0/adc_bus
    iq_split_0/adc_bus intensity_probe_0/adc_rail_bus
    intensity_rx_lowpass_0/filtered_valid intensity_probe_0/adc_valid
    intensity_rx_lowpass_0/filtered_i cordic_average_0/s_axis_i_tdata
    intensity_rx_lowpass_0/filtered_q cordic_average_0/s_axis_q_tdata
    intensity_rx_lowpass_0/filtered_valid cordic_average_0/s_axis_i_tvalid
    intensity_rx_lowpass_0/filtered_valid cordic_average_0/s_axis_q_tvalid
} {rx_link $source $sink}
# Remove the three old AXIS connections before rebuilding the calibration path.
foreach pin {cordic_average_0/m_axis_cartesian cordic_0/M_AXIS_DOUT cic_compiler_2/M_AXIS_DATA} {
    set net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins $pin]]
    if {[llength $net]} {delete_bd_objs $net}
}
if {![llength [get_bd_cells -quiet intensity_cal_q]]} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:cic_compiler:4.0 intensity_cal_q
    set_property -dict [list CONFIG.Filter_Type Decimation CONFIG.Number_Of_Stages 3 \
        CONFIG.Fixed_Or_Initial_Rate 8192 CONFIG.Input_Data_Width 16 CONFIG.Output_Data_Width 16 \
        CONFIG.Quantization Truncation CONFIG.Clock_Frequency 245.76 \
        CONFIG.Input_Sample_Frequency 245.76 CONFIG.Sample_Rate_Changes Fixed] [get_bd_cells intensity_cal_q]
    connect_bd_net $clk [get_bd_pins intensity_cal_q/aclk]
    foreach {name from to} {intensity_cal_i_slice 15 0 intensity_cal_q_slice 31 16} {
        create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice:1.0 $name
        set_property -dict [list CONFIG.DIN_WIDTH 32 CONFIG.DIN_FROM $from CONFIG.DIN_TO $to CONFIG.DOUT_WIDTH 16] [get_bd_cells $name]
    }
    create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat:2.1 intensity_cal_iq
    set_property -dict [list CONFIG.NUM_PORTS 2 CONFIG.IN0_WIDTH 16 CONFIG.IN1_WIDTH 16] [get_bd_cells intensity_cal_iq]
}
# Full-precision CICs retain all 16+3*log2(8192)=55 bits internally.
# The old Hogenauer truncation pruned five bits at the INPUT, causing phase bias.
foreach name {cic_compiler_2 intensity_cal_q} {
    set_property CONFIG.Quantization Full_Precision [get_bd_cells $name]
}
foreach name {intensity_cal_i_scale intensity_cal_q_scale} {
    if {![llength [get_bd_cells -quiet $name]]} {
        create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice:1.0 $name
    }
    set_property -dict [list CONFIG.DIN_WIDTH 56 CONFIG.DIN_FROM 54 CONFIG.DIN_TO 39 CONFIG.DOUT_WIDTH 16] [get_bd_cells $name]
}
foreach {source sink} {
    cordic_average_0/m_axis_cartesian_tdata intensity_cal_i_slice/Din
    cordic_average_0/m_axis_cartesian_tdata intensity_cal_q_slice/Din
    intensity_cal_i_slice/Dout cic_compiler_2/s_axis_data_tdata
    intensity_cal_q_slice/Dout intensity_cal_q/s_axis_data_tdata
    cordic_average_0/m_axis_cartesian_tvalid cic_compiler_2/s_axis_data_tvalid
    cordic_average_0/m_axis_cartesian_tvalid intensity_cal_q/s_axis_data_tvalid
    cic_compiler_2/m_axis_data_tdata intensity_cal_i_scale/Din
    intensity_cal_i_scale/Dout intensity_cal_iq/In0
    intensity_cal_q/m_axis_data_tdata intensity_cal_q_scale/Din
    intensity_cal_q_scale/Dout intensity_cal_iq/In1
    intensity_cal_iq/dout cordic_0/s_axis_cartesian_tdata
    cic_compiler_2/m_axis_data_tvalid cordic_0/s_axis_cartesian_tvalid
    cordic_0/m_axis_dout_tdata axis_tlast_gen_3/s_axis_tdata
    cordic_0/m_axis_dout_tvalid axis_tlast_gen_3/s_axis_tvalid
} {rx_link $source $sink}
connect_bd_intf_net [get_bd_intf_pins cordic_average_0/m_axis_cartesian] [get_bd_intf_pins system_ila_0/SLOT_1_AXIS]
foreach sink {axis_tlast_gen_3/s_axis system_ila_0/SLOT_0_AXIS system_ila_0/SLOT_5_AXIS} {
    connect_bd_intf_net [get_bd_intf_pins cordic_0/M_AXIS_DOUT] [get_bd_intf_pins $sink]
}
# Same rates, raw ADC interface and tile neighbours. Only the new RF band's
# parity is changed; helper uses a negative DDS frequency to retain RF phase sign.
set_property CONFIG.ADC_Nyquist11 1 [get_bd_cells usp_rf_data_converter_0]
update_module_reference [get_ips design_1_intensity_probe_0_0]
source $root/scripts/refresh_laser_pll_sources.tcl
validate_bd_design
save_bd_design
make_wrapper -files [get_files design_1.bd] -top
puts "INTENSITY_FILTERED_BD_VALIDATED"
