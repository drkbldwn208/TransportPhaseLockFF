# A7: independent ADC225/1 -> DAC229/3, FRA window diagnostics and optional IIR.
# Preserve all existing ADC/DAC sample rates and the original transport paths.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[current_project -quiet] eq ""} {open_project $root/TransportPhaseLockFF.xpr}
open_bd_design [get_files design_1.bd]
source $root/scripts/refresh_laser_pll_sources.tcl
set rfclk [get_bd_pins usp_rf_data_converter_0/clk_adc1]
set rfrst [get_bd_pins proc_sys_reset_0/peripheral_aresetn]
proc pll_connect {source sink} {
    if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins $sink]]]} {
        connect_bd_net [get_bd_pins $source] [get_bd_pins $sink]
    }
}
proc pll_intf {source sink} {
    if {![llength [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins $sink]]]} {
        connect_bd_intf_net [get_bd_intf_pins $source] [get_bd_intf_pins $sink]
    }
}
# A second AXI control interconnect avoids the first interconnect's 32-port limit.
if {![llength [get_bd_cells -quiet pll_extension_axi]]} {
    set_property CONFIG.NUM_MI 29 [get_bd_cells axi_interconnect_0]
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 pll_extension_axi
    set_property CONFIG.NUM_MI 25 [get_bd_cells pll_extension_axi]
    pll_intf axi_interconnect_0/M28_AXI pll_extension_axi/S00_AXI
    foreach pin {axi_interconnect_0/M28_ACLK pll_extension_axi/ACLK pll_extension_axi/S00_ACLK} {connect_bd_net $rfclk [get_bd_pins $pin]}
    foreach pin {axi_interconnect_0/M28_ARESETN pll_extension_axi/ARESETN pll_extension_axi/S00_ARESETN} {connect_bd_net $rfrst [get_bd_pins $pin]}
}
proc pll_slave {name kind index address dir1 dir2} {
    global rfclk rfrst
    if {[llength [get_bd_cells -quiet $name]]} {return}
    switch $kind {
        gpio {set vlnv xilinx.com:ip:axi_gpio:2.0; set bus S_AXI; set clk s_axi_aclk; set rst s_axi_aresetn}
        tone {set vlnv xilinx.com:hls:perturbation_gen:1.0; set bus s_axi_ctrl; set clk ap_clk; set rst ap_rst_n}
        demod {set vlnv xilinx.com:hls:demod_err:1.0; set bus s_axi_ctrl; set clk ap_clk; set rst ap_rst_n}
        dma {set vlnv xilinx.com:ip:axi_dma:7.1; set bus S_AXI_LITE; set clk s_axi_lite_aclk; set rst axi_resetn}
    }
    set cell [create_bd_cell -type ip -vlnv $vlnv $name]
    if {$kind eq "gpio"} {
        set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_GPIO2_WIDTH {32} \
            CONFIG.C_ALL_INPUTS $dir1 CONFIG.C_ALL_OUTPUTS [expr {!$dir1}] \
            CONFIG.C_ALL_INPUTS_2 $dir2 CONFIG.C_ALL_OUTPUTS_2 [expr {!$dir2}] \
            CONFIG.C_DOUT_DEFAULT {0x00000000} CONFIG.C_DOUT_DEFAULT_2 {0x00000000}] $cell
    }
    if {$kind eq "dma"} {
        set_property -dict [list CONFIG.c_addr_width {50} CONFIG.c_include_mm2s {0} \
            CONFIG.c_include_sg {0} CONFIG.c_m_axi_s2mm_data_width {128} \
            CONFIG.c_s_axis_s2mm_tdata_width {128} CONFIG.c_sg_length_width {26}] $cell
        connect_bd_net $rfclk [get_bd_pins $name/m_axi_s2mm_aclk]
    }
    set master [format "M%02d" $index]
    connect_bd_intf_net [get_bd_intf_pins pll_extension_axi/${master}_AXI] [get_bd_intf_pins $name/$bus]
    foreach pin [list $name/$clk pll_extension_axi/${master}_ACLK] {connect_bd_net $rfclk [get_bd_pins $pin]}
    foreach pin [list $name/$rst pll_extension_axi/${master}_ARESETN] {connect_bd_net $rfrst [get_bd_pins $pin]}
    assign_bd_address -offset $address -range 64K -target_address_space \
        [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $name/$bus/Reg] -force
}
# Six new GPIOs per loop. Read-only diagnostics cannot alter the feedback.
foreach {prefix block first address} {pll laser_pll_0 0 0xA02A0000 pll2 laser_pll_1 19 0xA10D0000} {
    if {$prefix eq "pll2" && ![llength [get_bd_cells -quiet $block]]} {
        create_bd_cell -type module -reference laser_pll_wrapper $block
        connect_bd_net $rfclk [get_bd_pins $block/clk]
        connect_bd_net $rfrst [get_bd_pins $block/rst_n]
    }
    set k 0
    foreach {suffix dir1 dir2 pin1 pin2} {
        fra_counts  1 1 fra_clip_samples fra_saturated_samples
        fra_extrema 1 1 fra_error_extrema fra_drive_extrema
        fra_samples 1 1 fra_outside_clip_samples fra_measured_samples
        iir         0 1 iir_control iir_status
        iir_feed    0 0 iir_b0 iir_b1
        iir_pole    0 0 iir_pole {}
    } {
        pll_slave ${prefix}_${suffix} gpio [expr {$first+$k}] [expr {$address+65536*$k}] $dir1 $dir2
        foreach {channel pin dir} [list gpio $pin1 $dir1 gpio2 $pin2 $dir2] {
            if {$pin eq ""} {continue}
            set gp ${prefix}_${suffix}/${channel}_io_[expr {$dir ? "i" : "o"}]
            if {$dir} {pll_connect $block/$pin $gp} else {pll_connect $gp $block/$pin}
        }
        incr k
    }
}
# Independent controls, monitor and HLS analyzer for the second optical loop.
set k 6
set address 0xA1000000
foreach {suffix kind dir1 dir2} {
    frequency gpio 0 0
    control gpio 0 0
    status gpio 1 1
    acquisition gpio 0 0
    acquisition_status gpio 1 1
    tracking gpio 0 1
    monitor gpio 0 1
    fra gpio 0 1
    fra_window gpio 0 0
    fra_tone tone 0 0
    fra_error demod 0 0
    fra_drive demod 0 0
    iq_dma dma 0 0
} {
    pll_slave pll2_$suffix $kind $k $address $dir1 $dir2
    incr k; incr address 65536
}
foreach {gpio pin} {
    frequency/gpio_io_o frequency_low frequency/gpio2_io_o frequency_high
    control/gpio_io_o control control/gpio2_io_o phase_offset
    status/gpio_io_i phase_status status/gpio2_io_i frequency_status
    acquisition/gpio_io_o acquisition_control acquisition/gpio2_io_o test_dc
    acquisition_status/gpio_io_i acquisition_status acquisition_status/gpio2_io_i fft_status
    tracking/gpio_io_o tracking_control tracking/gpio2_io_i tracking_status
    monitor/gpio_io_o monitor_control monitor/gpio2_io_i monitor_status
    fra/gpio_io_o fra_control fra/gpio2_io_i fra_status
    fra_window/gpio_io_o fra_settle_clocks fra_window/gpio2_io_o fra_measure_clocks
} {
    if {[string match *_i $gpio]} {pll_connect laser_pll_1/$pin pll2_$gpio} else {pll_connect pll2_$gpio laser_pll_1/$pin}
}
foreach {source sink} {
    pll2_fra_tone/perturb_err_out laser_pll_1/s_fra_tone
    pll2_fra_tone/ref_out laser_pll_1/s_fra_ref
    laser_pll_1/m_fra_error pll2_fra_error/probe_in
    laser_pll_1/m_fra_error_ref pll2_fra_error/ref_in
    laser_pll_1/m_fra_drive pll2_fra_drive/probe_in
    laser_pll_1/m_fra_drive_ref pll2_fra_drive/ref_in
} {pll_intf $source $sink}
pll_connect pll_fra_one/dout pll2_fra_tone/perturb_nco_out_TREADY
if {![llength [get_bd_cells -quiet pll2_iq_fifo]]} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:axis_data_fifo:2.0 pll2_iq_fifo
    set_property -dict [list CONFIG.TDATA_NUM_BYTES {16} CONFIG.FIFO_DEPTH {1024} \
        CONFIG.HAS_TLAST {1} CONFIG.IS_ACLK_ASYNC {0}] [get_bd_cells pll2_iq_fifo]
    connect_bd_net $rfclk [get_bd_pins pll2_iq_fifo/s_axis_aclk]
    pll_connect laser_pll_1/monitor_fifo_rst_n pll2_iq_fifo/s_axis_aresetn
    pll_intf laser_pll_1/m_monitor pll2_iq_fifo/S_AXIS
    pll_intf pll2_iq_fifo/M_AXIS pll2_iq_dma/S_AXIS_S2MM
    set_property CONFIG.NUM_SI 9 [get_bd_cells smartconnect_0]
    pll_intf pll2_iq_dma/M_AXI_S2MM smartconnect_0/S08_AXI
    assign_bd_address -target_address_space [get_bd_addr_spaces pll2_iq_dma/Data_S2MM]
}
set rfdc [get_bd_cells usp_rf_data_converter_0]
set_property -dict [list CONFIG.ADC_Slice11_Enable {true} \
    CONFIG.ADC_Data_Type11 {0} CONFIG.ADC_Decimation_Mode11 {1} CONFIG.ADC_Data_Width11 {8} \
    CONFIG.ADC_Mixer_Type11 {1} CONFIG.ADC_Mixer_Mode11 {2} CONFIG.ADC_Coarse_Mixer_Freq11 {3} \
    CONFIG.ADC_NCO_Freq11 {0} CONFIG.ADC_Nyquist11 {0} CONFIG.ADC_CalOpt_Mode11 {2} \
    CONFIG.DAC_Slice13_Enable {true} CONFIG.DAC_Data_Width13 {14} CONFIG.DAC_Interpolation_Mode13 {4} \
    CONFIG.DAC_Mixer_Mode13 {0} CONFIG.DAC_Mixer_Type13 {2} CONFIG.DAC_Coarse_Mixer_Freq13 {3} \
    CONFIG.DAC_NCO_Freq13 {0} CONFIG.DAC_NCO_Phase13 {0}] $rfdc
pll_intf usp_rf_data_converter_0/m11_axis laser_pll_1/s_axis
pll_intf laser_pll_1/m_axis usp_rf_data_converter_0/s13_axis
foreach analog {vin11 vout13} {
    if {![llength [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins usp_rf_data_converter_0/$analog]]]} {
        set before [get_bd_intf_ports]
        make_bd_intf_pins_external [get_bd_intf_pins usp_rf_data_converter_0/$analog]
        foreach port [get_bd_intf_ports] {if {$port ni $before} {set_property name $analog $port}}
    }
}
validate_bd_design
save_bd_design
make_wrapper -files [get_files design_1.bd] -top
puts "A7_DUAL_PLL_BD_VALIDATED"
