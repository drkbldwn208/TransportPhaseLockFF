# Source in an open project before updating the PLL module reference.
set fft_root [file normalize [file join [file dirname [info script]] ..]]
set fft_dir $fft_root/TransportPhaseLockFF.srcs/sources_1/ip
file mkdir $fft_dir
if {![llength [get_ips -quiet laser_pll_fft_core]]} {
    set fft_xci $fft_dir/laser_pll_fft_core/laser_pll_fft_core.xci
    if {[file exists $fft_xci]} {
        read_ip $fft_xci
    } else {
        create_ip -name xfft -vendor xilinx.com -library ip -version 9.1 \
            -module_name laser_pll_fft_core -dir $fft_dir
    }
}
set_property -dict [list \
    CONFIG.implementation_options {radix_2_lite_burst_io} \
    CONFIG.transform_length {1024} CONFIG.input_width {16} \
    CONFIG.phase_factor_width {16} CONFIG.scaling_options {scaled} \
    CONFIG.rounding_modes {convergent_rounding} CONFIG.aresetn {true} \
    CONFIG.ovflo {true} CONFIG.xk_index {true} \
    CONFIG.output_ordering {bit_reversed_order} \
    CONFIG.throttle_scheme {nonrealtime} CONFIG.target_clock_frequency {250} \
    CONFIG.memory_options_data {block_ram} \
    CONFIG.memory_options_phase_factors {block_ram}] [get_ips laser_pll_fft_core]
generate_target all [get_ips laser_pll_fft_core]
