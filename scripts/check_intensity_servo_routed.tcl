# Run with the implemented design open. All four I lanes must come from RFDC,
# not a constant driver, in the actual netlist that produced the bitstream.
set intensity_inputs [get_pins -hierarchical -filter {NAME =~ */fast_servo_controller_0/adc_bus*}]
if {[llength $intensity_inputs] != 64} {
    error "Expected 64 intensity ADC input pins, found [llength $intensity_inputs]"
}
set intensity_report [open $root/build/full_project/intensity_servo_routed.rpt w]
foreach pin $intensity_inputs {
    # Use the wire's leaf driver, not timing fan-in: timing fan-in traces through
    # the RFDC data output to its FABRIC_CLK and loses the ADC channel identity.
    set nets [get_nets -segments -of_objects $pin]
    set drivers [get_pins -leaf -of_objects $nets -filter {DIRECTION == OUT}]
    if {[llength $drivers] != 1 ||
        ![string match *usp_rf_data_converter_0*/rx0_u_adc/DATA_ADC1* [get_property NAME $drivers]]} {
        close $intensity_report
        error "Intensity receiver input $pin is not driven by ADC224/1 data: $drivers"
    }
    puts $intensity_report "$pin <- $drivers"
}
puts $intensity_report "PASS: all 64 intensity ADC input bits driven by RFDC in implemented netlist"
close $intensity_report
puts "PASS: all 64 intensity ADC input bits driven by RFDC in implemented netlist"
