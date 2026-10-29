# Rebuild after an internal IS03 RTL timing change with unchanged ports/BD.
# Reuse valid existing IP runs; full synthesis and routed timing still run.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[current_project -quiet] eq ""} {error "Open the existing project first"}
open_bd_design [get_files design_1.bd]
update_compile_order -fileset sources_1
update_module_reference [get_ips design_1_intensity_linearized_0_0]
validate_bd_design
save_bd_design
generate_target all [get_files design_1.bd]
puts [exec python3 $root/scripts/check_intensity_servo.py]
create_ip_run [get_files design_1.bd]
reset_run synth_1
foreach run [get_runs] {file mkdir [get_property DIRECTORY $run]}
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {![string match {*synth_design Complete*} [get_property STATUS [get_runs synth_1]]]} {
    error "Full synthesis failed after IS03 output-register change"
}
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
set status [get_property STATUS [get_runs impl_1]]
if {![string match {*route_design Complete*} $status] &&
    ![string match {Not started phys_opt_design (Post-Route)} $status]} {
    error "Routing failed: $status"
}
if {[get_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED [get_runs impl_1]]} {
    launch_runs impl_1 -to_step {phys_opt_design (Post-Route)} -jobs 4
    wait_on_run impl_1
    if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Post-route optimization failed"}
}
source $root/scripts/report_laser_pll_timing.tcl
