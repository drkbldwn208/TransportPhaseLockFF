# Full routed build; the user's shell monitor owns pynq_overlays/.
set root [file normalize [file join [file dirname [info script]] ..]]
set package $root/build/PDH_TUNABLE_PHOTON
file mkdir $package/reports
if {[catch {
    open_project $root/TransportPhaseLockFF.xpr
    if {[lsearch -exact $argv resume]<0} {source $root/scripts/add_pdh_tunable_photon.tcl}
    if {[lsearch -exact $argv prepare_only]>=0} {close_project; exit 0}
    set_property INCREMENTAL_CHECKPOINT {} [get_runs impl_1]
    if {[lsearch -exact $argv resume]>=0} {
        foreach run [get_runs] {
            if {[regexp -nocase {running|queued} [get_property STATUS $run]]} {reset_run $run}
        }
        reset_run synth_1
        launch_runs synth_1 -jobs 3
        wait_on_run synth_1
        if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed"}
        launch_runs impl_1 -to_step route_design -jobs 3
        wait_on_run impl_1
        if {![file exists $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper_routed.dcp]} {error "Routing failed"}
        if {[get_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED [get_runs impl_1]]} {
            launch_runs impl_1 -to_step {phys_opt_design (Post-Route)} -jobs 3
            wait_on_run impl_1
            if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Post-route optimization failed"}
        }
        source $root/scripts/report_laser_pll_timing.tcl
    } else {source $root/scripts/check_full_project_timing.tcl}
    source $root/scripts/check_intensity_servo_routed.tcl
    report_route_status -file $package/reports/route_status.rpt
    report_bus_skew -warn_on_violation -file $package/reports/bus_skew.rpt
    report_utilization -cells [get_cells -hierarchical -filter {NAME =~ *pdh_tones_0 && IS_PRIMITIVE == 0}] -file $package/reports/pdh_utilization.rpt
    report_utilization -cells [get_cells -hierarchical -filter {NAME =~ *photon_counting && IS_PRIMITIVE == 0}] -file $package/reports/photon_utilization.rpt
    report_timing -from [get_cells -hierarchical -filter {NAME =~ *pdh_tones* && IS_SEQUENTIAL}] -max_paths 15 -file $package/reports/pdh_timing.rpt
    report_cdc -file $package/reports/cdc.rpt
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
    puts "PDH_TUNABLE_PHOTON_BITSTREAM_COMPLETE $package"
} message options]} {
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
