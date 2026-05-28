# Vitis HLS / Vivado HLS script for the RFDC I/Q derotator IP.
#
# From this directory:
#
#   vitis_hls -f run_hls.tcl
#
# The target part is copied from TransportPhaseLockFF.xpr.

open_project rfdc_iq_derotator_prj
set_top rfdc_iq_derotator

add_files rfdc_iq_derotator.cpp
add_files rfdc_iq_derotator.h
add_files rfdc_iq_derotator_lut.h
add_files -tb tb_rfdc_iq_derotator.cpp

open_solution "solution1" -flow_target vivado
set_part {xczu49dr-ffvf1760-2-e}

# 245.76 MHz RFDC AXI/fabric clock: period = 1 / 245.76e6 = 4.069 ns.
create_clock -period 4.069 -name ap_clk

csim_design
csynth_design
export_design -format ip_catalog

exit
