# Finish the routed project and collect a matching PYNQ overlay. No board download.
set root [file normalize [file join [file dirname [info script]] ..]]
set out $root/build/laser_pll_overlay
open_project $root/TransportPhaseLockFF.xpr
set run [get_runs impl_1]
if {[get_property NEEDS_REFRESH $run]} {
    error "Implementation is stale; run check_full_project_timing.tcl first"
}
if {![string match {*route_design Complete*} [get_property STATUS $run]] &&
    ![string match {*write_bitstream Complete*} [get_property STATUS $run]]} {
    error "Complete routed implementation before exporting the overlay"
}
if {![string match {*write_bitstream Complete*} [get_property STATUS $run]]} {
    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
}
if {![string match {*write_bitstream Complete*} [get_property STATUS $run]]} {
    error "Bitstream generation failed; inspect impl_1/runme.log"
}
file mkdir $out
open_run impl_1
write_debug_probes -force $out/laser_pll.ltx
file copy -force $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper.bit $out/laser_pll.bit
file copy -force $root/TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh $out/laser_pll.hwh
file copy -force $root/python_scripts/laser_pll.py $out/laser_pll.py
file copy -force $root/python_scripts/laser_pll_bringup.ipynb $out/laser_pll_bringup.ipynb
puts "LASER_PLL_OVERLAY $out"
