# Timing fix: reuse the previous routed placement outside the small diagnostic.
# The normal full-board timing gate still applies before bitstream generation.
set root [file normalize [file join [file dirname [info script]] ..]]
open_project $root/TransportPhaseLockFF.xpr
set seed $root/build/intensity_fra/zero_register_attempt/design_1_wrapper_postroute_physopt.dcp
if {![file exists $seed]} {error "Run build_intensity_fra.tcl for a fresh implementation; no incremental seed exists"}
set_property INCREMENTAL_CHECKPOINT $seed [get_runs impl_1]
# A failing seed must not become the target slack: explicitly seek timing closure.
set_property -name INCREMENTAL_CHECKPOINT.MORE_OPTIONS -value {-directive TimingClosure} -objects [get_runs impl_1]
source $root/scripts/build_intensity_fra.tcl
