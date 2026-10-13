# Keep the working A8 overlay directory/archive intact while producing the R7 FRA release.
set root [file normalize [file join [file dirname [info script]] ..]]
set out $root/build/laser_pll_R7_FRA
open_project $root/TransportPhaseLockFF.xpr
set run [get_runs impl_1]
if {[get_property NEEDS_REFRESH $run]} {error "Implementation is stale"}
if {![string match {*route_design Complete*} [get_property STATUS $run]] &&
    ![string match {*write_bitstream Complete*} [get_property STATUS $run]] &&
    ![string match {*phys_opt_design*Complete*} [get_property STATUS $run]]} {error "Complete routing first"}
if {![string match {*write_bitstream Complete*} [get_property STATUS $run]]} {
    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
}
if {![string match {*write_bitstream Complete*} [get_property STATUS $run]]} {error "Bitstream generation failed"}
file mkdir $out
open_run impl_1
source $root/scripts/check_intensity_servo_routed.tcl
report_route_status -file $root/build/full_project/route_status.rpt
report_bus_skew -warn_on_violation -file $root/build/full_project/bus_skew.rpt
write_debug_probes -force $out/laser_pll.ltx
file copy -force $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper.bit $out/laser_pll.bit
file copy -force $root/TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh $out/laser_pll.hwh
puts "R7_RF_FRA_OVERLAY $out"
