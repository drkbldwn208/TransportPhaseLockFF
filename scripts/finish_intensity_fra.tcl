# Called with a timing-closed implementation open. Does not program hardware.
set out $root/build/intensity_calibration_R7
file mkdir $out/reports
set probes [get_cells -hierarchical -filter {NAME =~ *intensity_probe* && IS_SEQUENTIAL}]
report_timing -from $probes -max_paths 15 -file $out/reports/intensity_paths.rpt
report_timing -to $probes -max_paths 15 -append -file $out/reports/intensity_paths.rpt
source $root/scripts/check_intensity_servo_routed.tcl
report_route_status -file $out/reports/route_status.rpt
report_bus_skew -warn_on_violation -file $out/reports/bus_skew.rpt
write_debug_probes -force $out/TransportPhaseLockFF.ltx
# write_bitstream consumes this completed implementation; no further P&R steps.
close_design
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {![string match {*write_bitstream Complete*} [get_property STATUS [get_runs impl_1]]]} {error "Bitstream failed"}
file copy -force $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper.bit $out/TransportPhaseLockFF.bit
file copy -force $root/TransportPhaseLockFF.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh $out/TransportPhaseLockFF.hwh
foreach name {timing_summary utilization drc clock_interaction pll_setup_paths pll_hold_paths intensity_servo_routed} {
    file copy -force $root/build/full_project/$name.rpt $out/reports/
}
close_project
puts "INTENSITY_FRA_BITSTREAM_COMPLETE $out"
