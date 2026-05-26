# Vitis HLS / Vivado HLS script for the dwell_fcw_streamer IP.
#
# From this directory:
#
#   vitis_hls -f run_hls.tcl
#
# The target part is copied from TransportPhaseLockFF.xpr.

open_project dwell_fcw_streamer_prj
set_top dwell_fcw_streamer

add_files dwell_fcw_streamer.cpp
add_files dwell_fcw_streamer.h
add_files -tb tb_dwell_fcw_streamer.cpp

open_solution "solution1" -flow_target vivado
set_part {xczu49dr-ffvf1760-2-e}

# 245.76 MHz PL clock: period = 1 / 245.76e6 = 4.069 ns.
create_clock -period 4.069 -name ap_clk

csim_design
csynth_design
export_design -format ip_catalog

exit
