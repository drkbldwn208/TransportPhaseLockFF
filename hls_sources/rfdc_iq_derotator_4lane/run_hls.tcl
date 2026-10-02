# Vitis HLS / Vivado HLS script for the RFDC I/Q derotator IP.
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

open_project rfdc_iq_derotator_4lane_prj
set_top rfdc_iq_derotator_4lane

add_files rfdc_iq_derotator_4lane.cpp
add_files rfdc_iq_derotator_4lane.h
add_files rfdc_iq_derotator_4lane_lut.h
add_files -tb tb_rfdc_iq_derotator_4lane.cpp

open_solution "solution1" -flow_target vivado
set_part {xczu49dr-ffvf1760-2-e}

# 245.76 MHz RFDC AXI/fabric clock: period = 1 / 245.76e6 = 4.069 ns.
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
