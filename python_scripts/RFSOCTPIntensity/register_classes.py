from labscript_devices import register_classes


device_name = "RFSOCTPIntensity"

if "_already_registered" not in globals():
    register_classes(
        device_name,
        BLACS_tab="labscript_devices.RFSOCTPIntensity.tp_intensity_host_schedule.RFSOCTPIntensityTab",
    )
    _already_registered = True

