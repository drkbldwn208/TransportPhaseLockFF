# Inspect actual routed drivers. Supports both the historical raw path and INT2.
set intensity_report [open $root/build/full_project/intensity_servo_routed.rpt w]
set filtered_inputs [get_pins -quiet -hierarchical -filter {NAME =~ */intensity_rx_lowpass_0/i_data* || NAME =~ */intensity_rx_lowpass_0/q_data*}]
set intensity_inputs [get_pins -hierarchical -filter {NAME =~ */fast_servo_controller_0/adc_bus*}]
if {[llength $intensity_inputs] != 64} {error "Expected 64 PI input bits"}
if {[llength $filtered_inputs]} {
    if {[llength $filtered_inputs] != 128} {error "Expected 128 filter input bits"}
    set receiver_inputs $filtered_inputs
} else {set receiver_inputs $intensity_inputs}
foreach pin $receiver_inputs {
    set nets [get_nets -segments -of_objects $pin]
    set drivers [get_pins -leaf -of_objects $nets -filter {DIRECTION == OUT}]
    if {[llength $drivers] != 1 || ![string match *usp_rf_data_converter_0*/rx0_u_adc/DATA_ADC1* [get_property NAME $drivers]]} {
        close $intensity_report
        error "Intensity receiver $pin is not driven by ADC224/1: $drivers"
    }
    puts $intensity_report "$pin <- $drivers"
}
if {[llength $filtered_inputs]} {
    set used_bits [dict create]
    foreach pin $intensity_inputs {
        set nets [get_nets -quiet -segments -of_objects $pin]
        # INT2 replicates one I sample four times. Synthesis can remove redundant
        # hierarchical input connections; require all 16 distinct sample bits.
        if {![llength $nets]} {
            puts $intensity_report "$pin: redundant lane input removed by synthesis"
            continue
        }
        set drivers [get_pins -leaf -of_objects $nets -filter {DIRECTION == OUT}]
        if {[llength $drivers] != 1 || ![string match *intensity_rx_lowpass_0* [get_property NAME $drivers]]} {
            close $intensity_report
            error "PI input $pin is not driven by filtered I: $drivers"
        }
        regexp {adc_bus\[([0-9]+)\]$} $pin -> bit
        dict set used_bits [expr {$bit%16}] 1
        puts $intensity_report "$pin <- $drivers"
    }
    if {[dict size $used_bits] != 16} {error "Missing distinct filtered I bits at PI input: $used_bits"}
    puts $intensity_report "PASS: ADC224/1 I/Q drives filter; all 16 distinct filtered I bits drive the used PI lane inputs"
} else {puts $intensity_report "PASS: all 64 intensity ADC input bits driven by RFDC in implemented netlist"}
close $intensity_report
puts "PASS: intensity receiver connections in implemented netlist"

# Record the AMD CIC's dynamic-OPMODE warning context without changing placement.
set cic_report [open $root/build/full_project/intensity_cic_dsp.rpt w]
foreach cell [get_cells -hierarchical -filter {REF_NAME == DSP48E2 && (NAME =~ *cic_compiler_2* || NAME =~ *intensity_cal_q*)}] {
    if {![regexp {comb/gen_stages\[0\].*gen_split_accum\[0\]} $cell]} {continue}
    set loc [get_property LOC $cell]
    puts $cic_report "$cell at $loc"
    if {[regexp {DSP48E2_X([0-9]+)Y([0-9]+)} $loc -> x y]} {
        set below [get_sites -quiet DSP48E2_X${x}Y[expr {$y-1}]]
        puts $cic_report "Below: $below cells=[get_cells -quiet -of_objects $below]"
    }
    foreach pin [get_pins -of_objects $cell -filter {REF_PIN_NAME =~ OPMODE*}] {
        set net [get_nets -segments -of_objects $pin]
        set drivers [get_pins -leaf -of_objects $net -filter {DIRECTION == OUT}]
        puts $cic_report "$pin <- $drivers"
        foreach driver [get_cells -of_objects $drivers] {
            puts $cic_report "  [get_property REF_NAME $driver] INIT=[get_property -quiet INIT $driver]"
        }
    }
}
close $cic_report
