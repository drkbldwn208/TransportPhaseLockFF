# Run after add_intensity_fra.tcl, with the GUI closed. Never programs hardware.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[catch {
    if {[current_project -quiet] eq ""} {open_project $root/TransportPhaseLockFF.xpr}
    if {[get_property INCREMENTAL_CHECKPOINT [get_runs impl_1]] ne ""} {
        set_property -name INCREMENTAL_CHECKPOINT.MORE_OPTIONS -value {-directive TimingClosure} -objects [get_runs impl_1]
    }
    open_bd_design [get_files design_1.bd]
    update_module_reference [get_ips design_1_intensity_probe_0_0]
    source $root/scripts/check_full_project_timing.tcl
    source $root/scripts/finish_intensity_fra.tcl
} message options]} {
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
