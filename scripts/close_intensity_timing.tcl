# Continue from verified synthesis; explicitly target zero slack in incremental P&R.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[catch {
    open_project $root/TransportPhaseLockFF.xpr
    if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis is incomplete"}
    set seed $root/build/intensity_fra/registered_runtime_attempt.dcp
    set previous_route $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper_postroute_physopt.dcp
    if {[file exists $previous_route]} {file copy -force $previous_route $seed}
    if {![file exists $seed]} {error "Missing registered reference checkpoint"}
    set_property INCREMENTAL_CHECKPOINT $seed [get_runs impl_1]
    # Installed Vivado 2024.1 uses read_checkpoint -directive TimingClosure.
    # This targets zero slack, never changing the clock constraints.
    set_property -name INCREMENTAL_CHECKPOINT.MORE_OPTIONS -value {-directive TimingClosure} -objects [get_runs impl_1]
    reset_run impl_1 -from_step place_design
    launch_runs impl_1 -to_step route_design -jobs 4
    wait_on_run impl_1
    if {![file exists $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper_routed.dcp]} {error "Routing failed"}
    if {[get_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED [get_runs impl_1]]} {
        launch_runs impl_1 -to_step {phys_opt_design (Post-Route)} -jobs 4
        wait_on_run impl_1
        if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Post-route optimization failed"}
    }
    source $root/scripts/report_laser_pll_timing.tcl
    source $root/scripts/finish_intensity_fra.tcl
} message options]} {
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
