# Build both physical loopback modes on the existing beat-note ADC/DAC pair.
# Close the GUI project first. This script never programs hardware.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[catch {
    source $root/scripts/upgrade_laser_pll_loopback.tcl
    source $root/scripts/check_full_project_timing.tcl
    close_project
    source $root/scripts/export_laser_pll_overlay.tcl
    close_project
} message options]} {
    puts stderr [dict get $options -errorinfo]
    catch {close_project}
    exit 1
}
exit 0
