# Continue from a routed checkpoint, optimizing physical implementation only.
# No RTL edits, no synthesis reset, no clock-constraint relaxation, no board download.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[catch {
    open_project $root/TransportPhaseLockFF.xpr
    set run [get_runs impl_1]
    set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED true $run
    set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveExplore $run
    launch_runs impl_1 -to_step {phys_opt_design (Post-Route)} -jobs 4
    wait_on_run impl_1
    puts "POST_ROUTE_STATUS [get_property STATUS $run]"
    if {[get_property PROGRESS $run] ne "100%"} {error "Post-route optimization did not complete"}
    source $root/scripts/report_laser_pll_timing.tcl
    # Refresh final connectivity/skew reports after physical netlist optimization.
    report_route_status -file $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper_route_status.rpt
    report_bus_skew -file $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper_bus_skew_routed.rpt
    close_project
    source $root/scripts/export_laser_pll_overlay.tcl
    close_project
} message options]} {
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
