# Report and enforce setup/hold timing on the current completed implementation.
set root [file normalize [file join [file dirname [info script]] ..]]
set out $root/build/full_project
file mkdir $out
open_run impl_1
report_timing_summary -delay_type min_max -max_paths 20 -report_unconstrained -file $out/timing_summary.rpt
report_utilization -hierarchical -file $out/utilization.rpt
report_clock_interaction -file $out/clock_interaction.rpt
report_drc -file $out/drc.rpt
set pll_registers [get_cells -hierarchical -filter {NAME =~ *laser_pll_* && IS_SEQUENTIAL}]
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
