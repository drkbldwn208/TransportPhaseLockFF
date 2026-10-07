# Clean generated runs after BD/debug-probe changes; preserve the saved BD wiring.
# Close this project in the GUI before invoking. Does not program hardware.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[catch {
    open_project $root/TransportPhaseLockFF.xpr
    foreach run [get_runs] {
        set status [get_property STATUS $run]
        if {[regexp -nocase {running|queued|launching} $status]} {
            puts "STOPPING $run ($status)"
            stop_runs $run
        }
    }
    reset_run [get_runs]
    reset_target all [get_files design_1.bd]
    source $root/scripts/validate_laser_pll_project.tcl
    source $root/scripts/check_full_project_timing.tcl
    close_project
    source $root/scripts/export_laser_pll_overlay.tcl
} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
