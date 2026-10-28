# Resume checks/export from impl_1's completed routed checkpoint. No rebuild.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[catch {
    open_project $root/TransportPhaseLockFF.xpr
    source $root/scripts/report_laser_pll_timing.tcl
    set package $root/build/intensity_filtered_R7
    file mkdir $package/reports
    source $root/scripts/check_intensity_servo_routed.tcl
    report_route_status -file $package/reports/route_status.rpt
    report_bus_skew -warn_on_violation -file $package/reports/bus_skew.rpt
    set filters [get_cells -hierarchical -filter {NAME =~ *intensity_rx_lowpass* && IS_SEQUENTIAL}]
    report_timing -from $filters -max_paths 15 -file $package/reports/intensity_filter_paths.rpt
    report_timing -to $filters -max_paths 15 -append -file $package/reports/intensity_filter_paths.rpt
    write_debug_probes -force $package/TransportPhaseLockFF.ltx
    close_design
    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
    if {![string match {*write_bitstream Complete*} [get_property STATUS [get_runs impl_1]]]} {error "Bitstream failed"}
    file copy -force $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper.bit $package/TransportPhaseLockFF.bit
    file copy -force $root/TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh $package/TransportPhaseLockFF.hwh
    foreach name {timing_summary utilization drc clock_interaction pll_setup_paths pll_hold_paths intensity_servo_routed intensity_cic_dsp} {
        file copy -force $root/build/full_project/$name.rpt $package/reports/
    }
    close_project
    puts "INTENSITY_FILTERED_BITSTREAM_COMPLETE $package"
} message options]} {
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
