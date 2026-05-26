# Vitis HLS / Vivado HLS script for the SSR8 FIR decimator IP.
#
# From this directory:
#
#   vitis_hls -f run_hls.tcl
#
# The target part is copied from TransportPhaseLockFF.xpr.

open_project ssr8_fir_decimator_prj
set_top ssr8_fir_decimator

add_files ssr8_fir_decimator.cpp
add_files ssr8_fir_decimator.h
add_files -tb tb_ssr8_fir_decimator.cpp

open_solution "solution1" -flow_target vivado
set_part {xczu49dr-ffvf1760-2-e}

# 245.76 MHz RFDC AXI/fabric clock: period = 1 / 245.76e6 = 4.069 ns.
create_clock -period 4.069 -name ap_clk

csim_design
csynth_design
export_design -format ip_catalog

exit
