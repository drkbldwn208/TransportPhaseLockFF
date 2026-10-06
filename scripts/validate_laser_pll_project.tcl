# Revalidate the saved integration and regenerate its Vivado output products.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[current_project -quiet] eq ""} {open_project $root/TransportPhaseLockFF.xpr}
open_bd_design [get_files design_1.bd]
set src $root/TransportPhaseLockFF.srcs/sources_1/new
add_files -norecurse [glob $src/laser_pll*.sv $src/laser_pll*.v $src/laser_pll*.vh $src/laser_pll*.mem]
update_compile_order -fileset sources_1
update_module_reference [get_ips design_1_laser_pll_0_0]
foreach name {ssr4_fir_decimator_0 ssr4_fir_decimator_1} {
    if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins $name/s_axis_TVALID]]]} {
        connect_bd_net [get_bd_pins xlconstant_0/dout] [get_bd_pins $name/s_axis_TVALID]
    }
}
validate_bd_design
save_bd_design
generate_target all [get_files design_1.bd]
puts "PLL_PROJECT_VALIDATED"
