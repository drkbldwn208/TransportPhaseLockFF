# BLACS handoff: calibrated intensity-servo waveform format

Updated: 2026-11-02

The calibrated intensity servo accepts a requested optical-power waveform in
**mW**, with times in **seconds relative to the experimental hardware trigger**.
The RFSoC PYNQ server converts the waveform into FPGA commands before the shot.
BLACS should supply the original physical waveform, before applying the previous
ADC-setpoint or analog-output voltage conversion.

This describes the current repository implementation. The updated worker must
still be installed and checked in the BLACS environment; repository tests do not
establish that the laboratory installation has been updated.

## 1. Shot-script interface

Install the supplied `tp_intensity_host_schedule.py` in the existing
`labscript_devices/RFSOCTPIntensity/` package. The updated `RFSOCTPIntensity`
device provides:

```python
# tp_device is the existing RFSOCTPIntensity connection-table object.
tp_device.set_power_schedule(
    time_s=[0, 0.005, 0.030, 0.080, 0.100],
    power_mW=[0, 5.0, 10.0, 0, 0],
    sensor_mode="low_power",  # or "high_power"
)
```

This commands off for 0–5 ms, 5 mW for 5–30 ms, 10 mW for 30–80 ms, then off
until the waveform ends at 100 ms.

- Each power value is held until the next timestamp: **sample-and-hold, not
  linear interpolation**. Digitize smooth ramps into suitably spaced samples.
- Times must start at zero, increase strictly, and contain at least two points.
  Subtract the trigger time if the source waveform uses absolute shot times.
- Times and powers must be finite; powers must be nonnegative.
- A step requires one point at its change time, not duplicate timestamps.
- The final timestamp ends the waveform and returns the command to zero. Its
  power value is not held; use zero for clarity.
- The existing external experimental trigger starts playback. Uploading the
  waveform does not itself start the shot.

## 2. Shot HDF5 format

The device saves the waveform at:

```text
/devices/<device_name>/power_schedule
```

This is an `N × 2` float64 dataset:

| Column | Quantity | Units |
|---|---|---|
| 0 | Time relative to trigger | s |
| 1 | Requested optical power | mW |

Required dataset attributes:

```python
time_units = "s"
power_units = "mW"
sensor_mode = "low_power"  # or "high_power"
```

The supplied device implementation writes this dataset, and its worker reads it
during `transition_to_buffered`.

## 3. ZMQ upload format

Use a ZMQ REQ socket with the configured RFSoC endpoint, currently defaulting to
`tcp://192.168.1.154:5557`. Send one multipart request with exactly two frames.

**Frame 1:** UTF-8 JSON header, for example:

```json
{
  "cmd": "load_tp_intensity_power",
  "dtype": "<f8",
  "shape": [5, 2],
  "time_units": "s",
  "power_units": "mW",
  "sensor_mode": "low_power",
  "metadata": {
    "h5_path": "/path/to/shot.h5",
    "device_name": "tp_device"
  }
}
```

**Frame 2:** contiguous, row-major, little-endian float64 bytes containing the
table. There are **16 bytes per row**, with no `.npy` header or CSV text. The
`metadata` dictionary is optional provenance.

The supplied `send_power_to_rfsoc()` helper performs this serialization. An
upload response with `status="ok"` means the waveform DMA is armed, awaiting the
hardware trigger. It does not mean that the shot has completed. The reply also
reports `sensor_mode`, `power_full_scale_mW`, `power_per_code_mW`, `num_words`,
and `num_bytes`; the last two describe the packed DMA waveform.

JSON-only requests include:

```json
{"cmd": "get_status"}
```

```json
{"cmd": "wait_done", "timeout_s": 5.0}
```

Errors return `{"status": "error", "message": "..."}`. Treat failed uploads
as shot-preparation failures. Choose a completion timeout long enough for the
remaining trigger wait, shot duration, and recording tail.

## 4. Power units, attenuation modes, and calibration ownership

The current notebook configures these numerical ranges:

| Mode | Numerical full scale | Power-code step |
|---|---:|---:|
| `low_power` | 50 mW | 0.762939 µW |
| `high_power` | 200 mW | 3.051758 µW |

PYNQ converts physical power using the configured scale:

```python
power_code = round(power_mW * 65536 / full_scale_mW)
```

Codes are unsigned 16-bit values, 0–65535. The nominal full-scale value itself
would require code 65536 and is not representable. Code zero means optical off.
For example, 10 mW becomes approximately 13107 codes in low mode or 3277 codes
in high mode. These are numerical command resolutions, not claims about optical
noise or ADC precision.

**Keep this conversion on PYNQ.** BLACS should not hard-code either scale.
The actual loaded calibration determines the scale and allowed power range.
Nonzero requests outside the sensor calibration or available AOM power range
are rejected rather than silently extrapolated or clipped.

The mode declaration must match both the physical PD attenuation and the
configured FPGA calibration. An upload does **not** change the physical
attenuator or select/load another calibration automatically. Change attenuation
and configure the corresponding mode between shots with the output off, then
refresh the server configuration snapshot. Regenerate any prepacked waveforms
after a mode change.

The conversion responsibilities are:

1. **BLACS:** desired optical power in mW and trigger-relative times.
2. **PYNQ:** physical mW to linear-power reference codes and timed DMA commands.
3. **FPGA sensor LUT:** measured mixer ADC counts to the same linear-power scale.
4. **FPGA controller/feedforward and AOM inverse LUT:** power demand to actuator
   RF-amplitude codes.

BLACS must not apply the sensor inverse or AOM inverse a second time.

## 5. FPGA command packing and timing

This is handled by PYNQ; it is documented here for debugging the interface.

Each packed DMA word is a little-endian unsigned 32-bit integer:

```text
bits 31:16 = unsigned linear-power reference code
bits 15:0  = dwell duration in FPGA clocks minus one

word = (power_code << 16) | (dwell_clocks - 1)
```

The PL clock is 245.76 MHz, approximately 4.069 ns per clock. Each ordinary word
holds its value for 1–65536 clocks. PYNQ splits longer holds automatically and
appends a one-clock zero command at the endpoint. Absolute sample edges are
rounded to the nearest clock before calculating dwell lengths, avoiding
accumulated per-interval rounding error. Intervals that collapse below one clock
are rejected.

The existing `axi_dma_6` MM2S path feeds the dwell streamer. The external trigger
controls playback; network latency and Python scheduling do not set shot timing.

## 6. Server setup and per-shot records

Initialize the RFSoC clocks, RF settings, sensor/AOM tables, and controller once
using the intensity-servo notebook. Save a fresh `servo.configuration(ol)` JSON
snapshot from that same FPGA/table-loading session, then start the server in
its default attach-only mode:

```bash
python tp_intensity_zmq_server.py \
  --bitfile /path/to/TransportPhaseLockFF.bit \
  --servo-configuration-json servo_configuration_current.json \
  --shot-recording-json shot_recording.json
```

Do not reprogram the FPGA for every shot. After reprogramming, reload calibration
tables and regenerate the configuration snapshot. Only one process should own
the command DMA; do not run a competing notebook DMA controller alongside the
server. Stop intensity FRA measurements before experimental shots.

An example recording configuration is:

```json
{
  "directory": "/home/xilinx/jupyter_notebooks/intensity_shots",
  "decimation_log2": 6,
  "tail_s": 0.001
}
```

With recording enabled, the receive DMA is armed before the waveform DMA. The
recorder follows the actual shot activity and captures the configured tail.
The worker calls `wait_done` during `transition_to_manual`; the server saves the
record as an NPZ **on the RFSoC** and returns its path and quality information.
The worker stores this response in the shot HDF5 file:

```text
/results/tp_intensity_streamer
    attribute: shot_record_json
```

The NPZ is not automatically copied to the BLACS computer. Add a separate file
transfer if central archival of the time-domain arrays is required. Upload
metadata and the server reply are also stored in this HDF5 results group.

Without recording, completion is based on command-DMA delivery; DMA idle alone
does not prove that the final physical dwell has finished. Retain the normal
experiment timing, and use shot recording when actual playback completion must
be confirmed by this interface.

## 7. Legacy compatibility and initial validation

If the physical-power dataset is absent, the worker retains its old compiled
AO/`TP_INT_SCALE` route and labels those commands as ADC counts. That legacy
upload is rejected when the calibrated power controller is selected. An old
compiled NI analog-output trace has already been converted to volts: do not
simply relabel it as mW. Supply the explicit physical-power dataset for the new
controller.

The host serializer, HDF5 reader, server decoder, and encoder have repository
tests using simulated DMA/registers. After installing the worker, verify a short
off–constant-power–off shot and several settled optical powers in each
attenuation mode before using experimental ramps.

Related repository files:

- [Detailed power-upload documentation](intensity_power_upload.md)
- [BLACS device and worker](../python_scripts/tp_intensity_host_schedule.py)
- [RFSoC ZMQ server](../python_scripts/tp_intensity_zmq_server.py)
- [RFSoC waveform buffer controller](../python_scripts/tp_intensity_rfsoc_buffer.py)
- [Intensity-servo setup notebook](../python_scripts/intensity_servo.ipynb)
- [Shot-record documentation](intensity_shot_records.md)
