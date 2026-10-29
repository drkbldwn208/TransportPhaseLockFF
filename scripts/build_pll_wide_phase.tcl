# Keep the IS03 intensity datapath and primary PLL. Widen only PLL2's stage3/4
# representation to 640 turns full span; no extra fast-path registers.
set root [file normalize [file join [file dirname [info script]] ..]]
set work $root/build/phase_range_20261029
set package $root/build/intensity_IS03_PLL640_R7
file mkdir $package/reports
if {[catch {
    open_project $root/TransportPhaseLockFF.xpr
    open_bd_design [get_files design_1.bd]
    source $root/scripts/refresh_laser_pll_sources.tcl
    set_property CONFIG.STAGE3_RANGE_SHIFT 0 [get_bd_cells laser_pll_0]
    set_property CONFIG.STAGE3_RANGE_SHIFT 2 [get_bd_cells laser_pll_1]
    validate_bd_design
    save_bd_design
    set_property INCREMENTAL_CHECKPOINT $work/backup/previous_routed.dcp [get_runs impl_1]
    set_property -name INCREMENTAL_CHECKPOINT.MORE_OPTIONS -value {-directive TimingClosure} -objects [get_runs impl_1]
    source $root/scripts/check_full_project_timing.tcl
    source $root/scripts/check_intensity_servo_routed.tcl
    report_route_status -file $package/reports/route_status.rpt
    report_bus_skew -warn_on_violation -file $package/reports/bus_skew.rpt
    write_debug_probes -force $package/TransportPhaseLockFF.ltx
    puts [exec python3 $root/python_scripts/repair_intensity_hwh.py \
        $root/TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh \
        $root/TransportPhaseLockFF.gen/sources_1/bd/design_1/synth/design_1.v]
    close_design
    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
    if {![string match {*write_bitstream Complete*} [get_property STATUS [get_runs impl_1]]]} {error "Bitstream failed"}
    file copy -force $root/TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh $package/TransportPhaseLockFF.hwh
    file copy -force $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper.bit $package/TransportPhaseLockFF.bit
    foreach name {timing_summary utilization drc clock_interaction pll_setup_paths pll_hold_paths intensity_servo_routed intensity_cic_dsp} {
        file copy -force $root/build/full_project/$name.rpt $package/reports/
    }
    close_project
    puts "INTENSITY_LINEARIZED_BITSTREAM_COMPLETE $package"
    puts "PHASE_RANGE_BUILD_COMPLETE PLL1=160_turns PLL2=640_turns"
} message options]} {
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
