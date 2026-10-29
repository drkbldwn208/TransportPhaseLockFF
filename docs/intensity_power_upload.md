# Physical-power commands and two numerical ranges

The BLACS host sends the requested sample-and-hold waveform in **mW** and times
in **seconds relative to the experimental trigger**, plus the physical PD
attenuation mode. The PYNQ server runs on the RFSoC processing system (PS). It
converts that entire waveform before the shot and transfers packed commands
through DMA to the programmable logic (PL). Neither network timing nor Python
execution sets the experimental waveform timing.

## Meaning of the three kinds of code

- **ADC counts** are the measured mixer/demodulator output. Its response depends
  on PD attenuation and mixer compression.
- **Power codes** represent linear optical power. The selected sensor LUT maps
  ADC counts to these codes; the reference uses the same scale. The FPGA forms
  `error = reference_power - measured_power`.
- **Actuator codes** set the RF amplitude. The inverse AOM LUT converts the
  controller plus feedforward demand into DAC amplitude using the sin² fit.

The new notebook uses these ranges:

| Mode | Full scale | Command step | Sensor-LUT rounding bound |
|---|---:|---:|---:|
| `low_power` | 50 mW | 0.76294 µW | ±0.38147 µW |
| `high_power` | 200 mW | 3.05176 µW | ±1.52588 µW |

Conversion is `round(power_mW * 65536 / full_scale_mW)`. For example, 10 mW is
13107 codes in low mode and 3277 codes in high mode. Both mean approximately
10 mW. This does not improve ADC measurement resolution: your latest low-mode
calibration changes by 3.7–5.3 µW per ADC count, and high mode by 35–46 µW. The
finer power coordinate limits the *additional* LUT rounding. It is not a claim
about optical noise, DAC resolution, or achievable stability.

Both sensor RAM banks already exist. Separate ranges change their contents,
reference encoding and the existing `full_scale/A_eff` multiplier register.
There are **zero added LUTs, BRAMs, DSPs or pipeline clocks**. The AOM inverse
RAM and its normalized-transmission index are unchanged. The low-mode change
reduces physical controller headroom for a given internal numerical limit;
use high mode for demands beyond the measured low-mode range. Numerical full
scale is not an experimentally validated power limit: the helper also enforces
the sensor calibration and available AOM power ranges.

## Configure on PYNQ between shots

Follow `intensity_servo.ipynb` for clock/RF setup, sensor tables, controller
coefficients, and measured effective AOM power. The relevant calls are:

```python
sensor_luts = servo.make_sensor_luts(
    low_sensor, high_sensor,
    low_power_full_scale_mW=50.0, power_full_scale_mW=200.0)

servo.safe_off(ol)
servo.manual_power(ol, 0, power_full_scale_mW=200.0)  # Zero in either coordinate.
servo.load_calibration(ol, sensor_luts, output_lut)
servo.configure_controller(ol, coefficients, sensor_mode='low_power',
                           feedforward=feedforward_enabled)
servo.set_incident_power(ol, effective_power_mW)
servo.enable(ol)  # Reference is still zero.
```

To change physical attenuation and its corresponding calibration, finish the
shot, select zero, then call `safe_off()`, change the physical attenuation,
and call `configure_controller(..., sensor_mode='high_power')`, followed by
`enable()`. The helper preserves the estimated physical `A_eff` and rescales
its register automatically. Do not flip only the raw GPIO mode bit. Old packed
waveforms must be regenerated. Kp and integral/lead-lag corners retain their
physical meaning because both reference and measurement change scale, and the
output multiplier cancels that scale exactly apart from quantization.

Save a fresh configuration after all changes, for an attach-only server:

```python
Path('servo_configuration_current.json').write_text(
    json.dumps(servo.configuration(ol), indent=2))
```

A saved file must come from the **same uninterrupted FPGA/table-loading
session**. LUT contents have no readback; the server can check registers and
RF settings, but cannot prove RAM contents from the file alone. Reloading the
bitstream requires table initialization and a new snapshot. No automatic
physical attenuation switch is implied.

## BLACS / labscript host

Install the updated `tp_intensity_host_schedule.py` in the host's existing
`labscript_devices/RFSOCTPIntensity/` package. The copy supplied here does not
modify that separate installation automatically.

In the shot script, call the existing RFSOCTPIntensity device with the original
physical waveform, before any NI-AO or ADC-setpoint conversion:

```python
# Replace tp_device with your existing RFSOCTPIntensity connection-table object.
# 0–5 ms off, 5–30 ms at 5 mW, 30–80 ms at 10 mW, then off to 100 ms.
tp_device.set_power_schedule(
    [0, 0.005, 0.030, 0.080, 0.100],
    [0, 5.0,   10.0,  0,     0],
    sensor_mode='low_power')
```

Use the same digitization of a smooth ramp that you already use, supplying the
mW samples. Values are held from each time to the next; the final value is an
endpoint and the streamer returns to zero there. Times start at zero and must
increase strictly; sample edges are rounded to the nearest FPGA clock, so a
long waveform does not accumulate per-interval rounding error. A step requires
one point at its change time, not duplicate time points. The existing external trigger is unchanged.

The device saves an N×2 float64 dataset at
`/devices/<device_name>/power_schedule`, with `time_units`, `power_units` and
`sensor_mode` attributes. The worker uploads it during `transition_to_buffered`.
The server's conversion scale and reply are recorded in the H5 results.

Without this dataset, the worker retains its old compiled-AO/`TP_INT_SCALE`
path and explicitly labels the result ADC counts. That legacy upload is
rejected if the calibrated power controller is active. The old compiled NI
analog-output trace has already undergone voltage conversion; it is **not**
the original mW waveform and must not simply be relabelled.

## RFSoC server and direct notebook upload

Only one process may own the command DMA. Stop the notebook DMA owner before
starting the server. Attach to the already configured overlay without download:

```bash
python tp_intensity_zmq_server.py \
  --bitfile /path/to/TransportPhaseLockFF.bit \
  --servo-configuration-json servo_configuration_current.json \
  --shot-recording-json shot_recording.json
```

For example, `shot_recording.json` can contain:

```json
{"directory": "/home/xilinx/jupyter_notebooks/intensity_shots", "decimation_log2": 6, "tail_s": 0.001}
```

The recorder uses the selected mode's physical scale automatically. A supplied
`power_per_code` override must agree with that scale. For a separate notebook
workflow, use the existing overlay directly:

```python
buffer = tp.TpIntensityBufferController(overlay=ol, shot_recording=shot_recording)
buffer.load_power_and_arm(time_s, power_mW, sensor_mode='low_power')
# Send the ordinary experimental trigger, then:
result = buffer.wait_done(timeout_s=5)
print(result['shot_record']['path'])
```

The server verifies the declared mode against the configured table; it does
not infer the physical attenuator position. Wrong units, stale mode/scale,
unreachable power or sub-clock holds are rejected before command DMA starts.
Prepacked commands are still supported for debugging with explicit
`metadata={'command_units':'power_codes', 'sensor_mode':..., 'power_full_scale_mW':...}`.
Prefer physical-power upload to avoid reusing codes from the wrong mode.

## Verification scope

`test_intensity_linearized_helper.py` checks both LUT ranges, quantization,
mode switching and unchanged physical AOM conversion. `test_intensity_power_upload.py`
checks host payload/H5 decoding through the actual server decoder and waveform
encoder, command duration/final zero, and rejection before DMA. Its DMA and
registers are simulated; it is not a board or BLACS installation test. Existing
RTL is unchanged by this software feature. Verify a few settled optical powers
in each attenuation mode before experimental shots.
