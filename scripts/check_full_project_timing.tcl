# Full project synthesis and implementation through route_design. No hardware download.
set root [file normalize [file join [file dirname [info script]] ..]]
set out $root/build/full_project
file mkdir $out
if {[current_project -quiet] eq ""} {open_project $root/TransportPhaseLockFF.xpr}
# Use actual OOC runs for the new inferred XCI/module reference.
config_ip_cache -disable_cache
update_compile_order -fileset sources_1
generate_target all [get_files design_1.bd]
create_ip_run [get_files design_1.bd]
create_ip_run [get_files */laser_pll_fft_core.xci]
reset_run [get_runs design_1_laser_pll_0_0_synth_1]
reset_run synth_1
foreach run [get_runs] {file mkdir [get_property DIRECTORY $run]}
launch_runs synth_1 -jobs 4
wait_on_run synth_1
puts "FULL_PROJECT_SYNTH_STATUS [get_property STATUS [get_runs synth_1]]"
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
    error "Full project synthesis did not complete; inspect .runs/*/runme.log"
}
if {![file exists $root/TransportPhaseLockFF.gen/sources_1/bd/design_1/ip/design_1_laser_pll_0_0/design_1_laser_pll_0_0.dcp]} {
    error "PLL checkpoint missing: revalidate BD and rebuild without editing RTL during the run"
}
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
puts "FULL_PROJECT_IMPL_STATUS [get_property STATUS [get_runs impl_1]]"
if {![string match {*route_design Complete*} [get_property STATUS [get_runs impl_1]]]} {
    error "Full project routing did not complete; inspect impl_1/runme.log"
}
open_run impl_1
report_timing_summary -delay_type min_max -max_paths 20 -report_unconstrained -file $out/timing_summary.rpt
report_utilization -hierarchical -file $out/utilization.rpt
report_clock_interaction -file $out/clock_interaction.rpt
report_drc -file $out/drc.rpt
set pll_registers [get_cells -hierarchical -filter {NAME =~ *laser_pll_0* && IS_SEQUENTIAL}]
# Check both sides of the PLL boundary without collecting every internal pin.
report_timing -from $pll_registers -delay_type max -max_paths 20 -file $out/pll_setup_paths.rpt
report_timing -to $pll_registers -delay_type max -max_paths 20 -append -file $out/pll_setup_paths.rpt
report_timing -to $pll_registers -delay_type min -max_paths 20 -file $out/pll_hold_paths.rpt
set setup_slack [get_property SLACK [get_timing_paths -max_paths 1]]
set hold_slack [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "FULL_PROJECT_WNS $setup_slack"
puts "FULL_PROJECT_WHS $hold_slack"
puts "FULL_PROJECT_REPORTS $out"
if {$setup_slack < 0 || $hold_slack < 0} {
    error "Full project timing failed; inspect $out/timing_summary.rpt"
}
