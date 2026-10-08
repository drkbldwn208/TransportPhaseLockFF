# Refresh the RTL dependency list of the existing PLL block without changing
# its ports, GPIO settings or BD wiring. Requires an open project and BD.
set pll_source_root [file normalize [file join [file dirname [info script]] ..]]
set pll_source_dir $pll_source_root/TransportPhaseLockFF.srcs/sources_1/new
foreach pll_source_file [glob $pll_source_dir/laser_pll*.sv $pll_source_dir/laser_pll*.v \
    $pll_source_dir/laser_pll*.vh $pll_source_dir/laser_pll*.mem] {
    if {![llength [get_files -quiet $pll_source_file]]} {
        add_files -norecurse $pll_source_file
    }
}
set pll_include_dirs [get_property include_dirs [get_filesets sources_1]]
if {$pll_source_dir ni $pll_include_dirs} {
    lappend pll_include_dirs $pll_source_dir
    set_property include_dirs $pll_include_dirs [get_filesets sources_1]
}
update_compile_order -fileset sources_1
update_module_reference [get_ips design_1_laser_pll_0_0]
