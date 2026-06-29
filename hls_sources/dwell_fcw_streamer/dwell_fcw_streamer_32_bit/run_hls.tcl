# Vitis HLS / Vivado HLS script for the dwell_fcw_streamer IP.
#
# From this directory:
#
#   vitis_hls -f run_hls.tcl
#
# Optional:
#
#   HLS_STEP=csim   vitis_hls -f run_hls.tcl
#   HLS_STEP=export vitis_hls -f run_hls.tcl
#
# The target part is copied from TransportPhaseLockFF.xpr.

open_project dwell_fcw_streamer_32_prj
set_top dwell_fcw_streamer_32

add_files dwell_fcw_streamer_32.cpp
add_files dwell_fcw_streamer_32.h
add_files -tb tb_dwell_fcw_streamer_32.cpp

open_solution "solution1" -flow_target vivado
set_part {xczu49dr-ffvf1760-2-e}

# 245.76 MHz PL clock: period = 1 / 245.76e6 = 4.069 ns.
create_clock -period 4.069 -name ap_clk

csim_design

if {![info exists ::env(HLS_STEP)]} {
    set hls_step "export"
} else {
    set hls_step $::env(HLS_STEP)
}

if {$hls_step eq "csim"} {
    exit
} elseif {$hls_step eq "export"} {
    csynth_design
    export_design -format ip_catalog
} else {
    puts "ERROR: HLS_STEP must be csim or export"
    exit 1
}

exit
