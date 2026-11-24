# Remove only the diagnostics added to the two laser PLLs. Open project/BD first.
# Original 2:1 transport PLL, intensity servo/captures and PDH remain connected.
set removed_cells {system_ila_0 axi_dma_3 pll2_iq_dma pll_iq_fifo pll2_iq_fifo pll_monitor pll2_monitor pll_rf_source}
foreach prefix {pll pll2} {
    foreach suffix {fra fra_window fra_tone fra_error fra_drive fra_counts fra_extrema fra_samples} {
        lappend removed_cells ${prefix}_${suffix}
    }
}
foreach name $removed_cells {
    set cell [get_bd_cells -quiet $name]
    if {[llength $cell]} {delete_bd_objs $cell}
}

# Compact vacant AXI slots while retaining every surviving peripheral address.
# Save the clock/reset nets of each master: some peripherals use the RF clock,
# others the PS clock. Do not infer the clock from the new slot number.
proc compact_axi {block direction count_property} {
    set kept {}
    foreach pin [lsort [get_bd_intf_pins -of_objects [get_bd_cells $block]]] {
        set leaf [file tail $pin]
        if {![regexp "^${direction}\[0-9\]\[0-9\]_AXI$" $leaf]} {continue}
        set net [get_bd_intf_nets -quiet -of_objects $pin]
        set peers {}
        if {[llength $net]} {
            foreach peer [get_bd_intf_pins -of_objects $net] {
                if {$peer ne $pin} {lappend peers $peer}
            }
        }
        set clocks {}
        foreach suffix {ACLK ARESETN} {
            set clock_pin [get_bd_pins -quiet $block/[string range $leaf 0 2]_$suffix]
            set clock_net [get_bd_nets -quiet -of_objects $clock_pin]
            dict set clocks $suffix $clock_net
            if {[llength $clock_net]} {disconnect_bd_net $clock_net $clock_pin}
        }
        if {[llength $peers]} {lappend kept [list $peers $clocks]}
        if {[llength $net]} {delete_bd_objs $net}
    }
    set_property CONFIG.$count_property [llength $kept] [get_bd_cells $block]
    set index 0
    foreach entry $kept {
        lassign $entry peers clocks
        set slot [format "%s%02d" $direction $index]
        connect_bd_intf_net [get_bd_intf_pins $block/${slot}_AXI] [get_bd_intf_pins $peers]
        dict for {suffix net} $clocks {
            set pin [get_bd_pins -quiet $block/${slot}_$suffix]
            if {[llength $pin] && [llength $net]} {connect_bd_net -net $net $pin}
        }
        incr index
    }
}
compact_axi axi_interconnect_0 M NUM_MI
compact_axi pll_extension_axi M NUM_MI
compact_axi smartconnect_0 S NUM_SI

# Remove orphan nets before refreshing the shortened module interfaces.
foreach net [get_bd_intf_nets] {
    if {[llength [get_bd_intf_pins -quiet -of_objects $net]] < 2 &&
        ![llength [get_bd_intf_ports -quiet -of_objects $net]]} {delete_bd_objs $net}
}
foreach net [get_bd_nets] {
    if {[llength [get_bd_pins -quiet -of_objects $net]] < 2 &&
        ![llength [get_bd_ports -quiet -of_objects $net]]} {delete_bd_objs $net}
}
source $root/scripts/refresh_laser_pll_sources.tcl
update_module_reference [get_ips design_1_intensity_rx_lowpass_0_0]

# Refreshing the PLL can detach the last endpoint of an obsolete RF-test net.
foreach net [get_bd_intf_nets] {
    if {![llength [get_bd_intf_pins -quiet -of_objects $net]] &&
        ![llength [get_bd_intf_ports -quiet -of_objects $net]]} {delete_bd_objs $net}
}
foreach net [get_bd_nets] {
    if {![llength [get_bd_pins -quiet -of_objects $net]] &&
        ![llength [get_bd_ports -quiet -of_objects $net]]} {delete_bd_objs $net}
}

# DAC229/2 was already muted (ENABLE_RF_SOURCE=0). Preserve that state without
# the retired RF-FRA source ports. Its converter settings/clock are unchanged.
if {![llength [get_bd_cells -quiet pll_unused_dac_zero]]} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 pll_unused_dac_zero
    set_property -dict [list CONFIG.CONST_WIDTH 224 CONFIG.CONST_VAL 0] [get_bd_cells pll_unused_dac_zero]
}
connect_bd_net [get_bd_pins pll_unused_dac_zero/dout] [get_bd_pins usp_rf_data_converter_0/s12_axis_tdata]
connect_bd_net [get_bd_pins xlconstant_2/dout] [get_bd_pins usp_rf_data_converter_0/s12_axis_tvalid]
validate_bd_design
save_bd_design
