# Repair the main project's PLL source list and verify full-project synthesis.
# Source in its Tcl console with runs stopped, or run in batch with the GUI
# project closed. Preserves the saved BD wiring and does not build a bitstream.
set root [file normalize [file join [file dirname [info script]] ..]]
set opened_project [expr {[current_project -quiet] eq ""}]
if {$opened_project} {open_project $root/TransportPhaseLockFF.xpr}
open_bd_design [get_files design_1.bd]
source $root/scripts/refresh_laser_pll_sources.tcl
save_bd_design
set fft_xci [get_files */laser_pll_fft_core.xci]
set_property generate_synth_checkpoint true $fft_xci
generate_target all $fft_xci
generate_target all [get_files design_1.bd]
create_ip_run [get_files design_1.bd]
create_ip_run $fft_xci
reset_run [get_runs design_1_laser_pll_0_0_synth_1]
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
puts "PLL_SOURCE_REPAIR_STATUS [get_property STATUS [get_runs design_1_laser_pll_0_0_synth_1]]"
puts "PROJECT_SOURCE_REPAIR_STATUS [get_property STATUS [get_runs synth_1]]"
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
    error "Project synthesis did not complete; inspect .runs/*/runme.log"
}
if {$opened_project} {close_project}
