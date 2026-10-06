# Standalone implementation checks internal PLL timing, without rebuilding the
# unrelated transport project. Run: vivado -mode batch -source this_file.tcl
set root [file normalize [file join [file dirname [info script]] ..]]
set src [file join $root TransportPhaseLockFF.srcs sources_1 new]
set out [file join $root build laser_pll_timing]
file mkdir $out
create_project -in_memory -part xczu49dr-ffvf1760-2-e
set_property include_dirs [list $src] [current_fileset]
read_verilog -sv [glob $src/laser_pll*.sv]
read_verilog $src/laser_pll_dac.v
read_verilog -sv $root/tests/laser_pll_timing_top.sv
add_files $src/laser_pll_sine.mem
# Work outside the source tree: Vivado cleans staged memory files on exit.
file copy -force $src/laser_pll_sine.mem $out/laser_pll_sine.mem
cd $out
synth_design -top laser_pll_timing_top -part xczu49dr-ffvf1760-2-e -mode out_of_context
create_clock -name pll_clk -period 4.069010417 [get_ports clk]
# The harness registers, not ideal zero-delay ports, launch/capture PLL data.
# Outer harness ports are outside this block timing check.
opt_design
place_design
phys_opt_design
route_design
report_timing_summary -file $out/timing_summary.rpt
report_utilization -file $out/utilization.rpt
report_drc -file $out/drc.rpt
write_checkpoint -force $out/laser_pll_routed.dcp
puts "PLL_TIMING_WNS [get_property SLACK [get_timing_paths -max_paths 1]]"
puts "PLL_TIMING_WHS [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]"
if {[get_property SLACK [get_timing_paths -max_paths 1]] < 0 ||
    [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]] < 0} {
    error "PLL timing failed; inspect timing_summary.rpt"
}
