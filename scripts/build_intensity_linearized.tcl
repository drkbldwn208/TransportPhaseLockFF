# Rebuild the original project. No FPGA programming and no overlays/ copies.
set root [file normalize [file join [file dirname [info script]] ..]]
set work $root/build/intensity_linearized
set package $root/build/intensity_linearized_R7
file mkdir $work/backup
file mkdir $package/reports
if {[catch {
    foreach name {TransportPhaseLockFF.xpr TransportPhaseLockFF.srcs/sources_1/bd/design_1/design_1.bd} {
        set target $work/backup/[file tail $name]
        if {![file exists $target]} {file copy $root/$name $target}
    }
    set previous $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper_routed.dcp
    set backup $work/backup/previous_routed.dcp
    if {![file exists $backup] && [file exists $previous]} {file copy $previous $backup}
    set old_hwh $root/TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh
    if {![file exists $work/backup/design_1.hwh]} {file copy $old_hwh $work/backup/design_1.hwh}
    open_project $root/TransportPhaseLockFF.xpr
    set core_only [expr {[lsearch -exact $argv core_only] >= 0}]
    if {!$core_only} {source $root/scripts/add_intensity_linearized.tcl}
    set incremental $backup
    foreach argument $argv {
        if {[string match {checkpoint=*} $argument]} {
            set incremental [file normalize [string range $argument 11 end]]
            if {![file exists $incremental]} {error "Missing incremental checkpoint: $incremental"}
        }
    }
    if {[file exists $incremental]} {
        set_property INCREMENTAL_CHECKPOINT $incremental [get_runs impl_1]
        set_property -name INCREMENTAL_CHECKPOINT.MORE_OPTIONS -value {-directive TimingClosure} -objects [get_runs impl_1]
    }
    if {$core_only} {
        source $root/scripts/rebuild_intensity_linearized_core.tcl
    } else {
        source $root/scripts/check_full_project_timing.tcl
    }
    source $root/scripts/check_intensity_servo_routed.tcl
    report_route_status -file $package/reports/route_status.rpt
    report_bus_skew -warn_on_violation -file $package/reports/bus_skew.rpt
    set registers [get_cells -hierarchical -filter {NAME =~ *intensity_linearized* && IS_SEQUENTIAL}]
    report_timing -from $registers -max_paths 20 -file $package/reports/intensity_controller_paths.rpt
    report_timing -to $registers -max_paths 20 -append -file $package/reports/intensity_controller_paths.rpt
    write_debug_probes -force $package/TransportPhaseLockFF.ltx
    # Correct Vivado's duplicate ILA metadata before the bitstream appears, so
    # an external overlay monitor also copies the verified matching HWH.
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
} message options]} {
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
