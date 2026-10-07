# Read-only audit of the routed checkpoint, including legacy clock/IO warnings.
set root [file normalize [file join [file dirname [info script]] ..]]
set out $root/build/full_project
open_checkpoint $root/TransportPhaseLockFF.runs/impl_1/design_1_wrapper_routed.dcp
report_cdc -details -file $out/cdc.rpt
report_clocks -file $out/clocks.rpt
report_utilization -file $out/utilization_summary.rpt
report_clock_networks -file $out/clock_networks.rpt
puts "ROUTED_CLOCK_AUDIT_COMPLETE"
exit 0
