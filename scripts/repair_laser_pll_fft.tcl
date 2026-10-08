# Regenerate and verify only the standalone FFT's OOC output products.
# Source in the main project's Tcl console with runs stopped, or run in batch
# after closing the GUI project. Does not change the BD or program hardware.
set root [file normalize [file join [file dirname [info script]] ..]]
set opened_project [expr {[current_project -quiet] eq ""}]
if {$opened_project} {open_project $root/TransportPhaseLockFF.xpr}
set fft_xci [get_files */laser_pll_fft_core.xci]
set fft_run [get_runs laser_pll_fft_core_synth_1]
reset_run $fft_run
set_property generate_synth_checkpoint true $fft_xci
reset_target all $fft_xci
generate_target all $fft_xci
create_ip_run $fft_xci
launch_runs $fft_run -jobs 1
wait_on_run $fft_run
puts "FFT_REPAIR_STATUS [get_property STATUS $fft_run]"
if {[get_property PROGRESS $fft_run] ne "100%"} {
    error "FFT synthesis did not complete; inspect its runme.log"
}
if {$opened_project} {close_project}
