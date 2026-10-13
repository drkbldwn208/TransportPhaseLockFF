# Restore ADC224/1's interface connection without changing RFDC or PI settings.
# R8 left orphan scalar nets on these pins. They override the AXIS interface
# and cause generated RTL to tie the receiver's data and valid inputs to zero.
foreach signal {tdata tvalid} {
    set pin [get_bd_pins usp_rf_data_converter_0/m01_axis_$signal]
    foreach net [get_bd_nets -quiet -of_objects $pin] {
        set pins [get_bd_pins -quiet -of_objects $net]
        if {[llength $pins] == 1 && [llength [get_bd_ports -quiet -of_objects $net]] == 0} {
            puts "Removing orphan intensity ADC net: $net"
            delete_bd_objs $net
        }
    }
}
set adc_net [get_bd_intf_nets -of_objects [get_bd_intf_pins usp_rf_data_converter_0/m01_axis]]
set receiver_net [get_bd_intf_nets -of_objects [get_bd_intf_pins iq_split_0/s_axis]]
if {[llength $adc_net] != 1 || $adc_net ne $receiver_net} {
    error "ADC224/1 is not connected to iq_split_0; do not build"
}
puts "INTENSITY_SERVO_INTERFACE_RESTORED; generated HWH/RTL must also pass check_intensity_servo.py"
