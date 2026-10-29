# Intensity records, tuning and slow power estimation

The shot logger observes the new intensity controller; it adds **no registers
to the feedback path**. The existing calibration/FRA recorder and its frame
format are unchanged. Recording is optional and initially disabled in the
RFSoC command server.

## What starts and stops a record

1. Python allocates the receive buffer and arms the dedicated S2MM DMA.
2. Python arms the logger, then starts the existing `axi_dma_6` command MM2S.
3. The external experimental trigger starts `dwell_fcw_streamer_32`. The logger
   starts on its `active` rising edge, sampling the controller reference, error,
   measured power, actual actuator command and raw ADC together.
4. The streamer `active` falling edge starts a programmable tail, normally 1 ms.
5. The logger attaches TLAST to its last uniformly spaced sample. Python waits
   for the **receive capture** to finish, then saves the record on the RFSoC.

Command-DMA idle alone is insufficient to identify the physical end of a shot:
the AXI/HLS input buffering can accept the final command before its dwell has
finished. Receive completion supplies an independent end-of-shot check.

One record is held back inside the logger until the next sample or the end of
the shot. This monitoring latency does not delay the actuator. Backpressure can
drop monitor samples but cannot stall the controller. Such a record has its
overflow flag set and must not be used for optimization or spectral analysis.

## Sampling and memory

At a 245.76 MHz FPGA clock, `D=6` gives 3.84 MS/s, 16 bytes per sample and
61.44 MB/s. A 100 ms shot plus a 1 ms tail occupies about **6.2 MB**. Nyquist is
1.92 MHz; this rate can resolve a 500 kHz oscillation. `D=8` uses a quarter of
the memory but Nyquist is only 480 kHz, so it cannot establish stability at or
above 500 kHz.

The 6.2 MB figure is the raw DMA buffer. Saved NPZ files also contain decoded
physical arrays and metadata; their compressed disk size depends on the data
and can exceed the raw-buffer size. The S2MM length register permits at most
67,108,863 bytes (4,194,303 complete frames), even if more RAM is available.

The logger takes point samples rather than averaging. It does not add a new
antialias filter. The existing receiver FIR suppresses the RF mixing image, but
its 1.5 MHz passband does not make heavy diagnostic decimation alias-free. Use
`D=6` for the initial loop checks; compare with a shorter, faster capture when
identifying unexpected spectral features. Never interpret an overflowed or
truncated record as a uniformly sampled full shot.

The buffer planner refuses a record above its explicit memory budget; it never
silently decreases the sampling rate. If the actual waveform lasts longer than
the allocated buffer, the logger produces TLAST and marks the record truncated.

## Record format

The 128-bit hardware frame has four little-endian uint32 words:

| Word | Bits | Contents |
|---|---|---|
| 0 | 31:0 | Signed error in Q17.8 power codes |
| 1 | 15:0 / 31:16 | Reference / measured linear power codes |
| 2 | 15:0 / 31:16 | Actual actuator code / signed raw ADC code |
| 3 | 15:0 / 31:16 | Flags / reserved zero |

Flag bits are 0 actuator clipping, 1 sensor outside its calibration, 2
controller saturation, 3 invalid ADC, 4 legacy controller selected, and 5
configuration update. Flags are ORed between sample strobes, so a brief fault
cannot disappear merely because the saved waveform was downsampled. Flags in
the final frame also include the end of the tail after its sample timestamp.

The NPZ preserves these raw words plus `time_s`, `reference_power`,
`measured_power`, `error_power`, `actuator_codes`, `raw_adc_counts`,
`sample_flags`, `valid`, `clipped`, `complete` and `metadata_json`. Power values
use `power_per_code`; absent an explicit physical conversion, they remain
linear power counts rather than pretending to be mW. Reference/measured/error
are the controller's sampled signals, not a deconvolution of detector or AOM
delay. The metadata must preserve the selected sensor mode, power units,
calibration hashes, controller settings, feedforward settings and gain scale.

Range warnings during intentional zero reference are retained. They do not
invalidate illuminated portions of a shot, but the clamped sensor result there
must not be interpreted as a measured dark optical power. Tracking RMS and
overshoot calculations use illuminated samples only. The software separately
reports the largest actual actuator command during intended optical-off.

A zero-to-positive reference step necessarily precedes the measured optical
response by the approximately 1.087 µs plant delay. `shot_metrics` therefore
allows at most 10 µs of startup grace for **below-calibration-only** ADC samples,
provided the record contains the selected calibration minimum and an observed
preceding zero reference. These samples retain their invalid/range flags and
are excluded from measured power RMS and the ringing PSD. Their time/fraction
is reported. No power is invented for these invalid samples. The record is
rejected if their combined duration exceeds
`maximum_excluded_startup_fraction=0.001` of illuminated samples (0.1% by
default), in addition to the 10 µs limit after each observed rise. Keep these
explicit limits fixed during an optimization round, and review excluded time
when comparing rise times: this sensor cannot score the portion below its
calibration range. Above-range, persistent below-range,
clipping and other faults remain invalid. Set `startup_grace_s=0` to disable
this allowance; larger than 10 µs is rejected. Old records without known ADC
limits get no implicit grace. Because flags are ORed over each decimation
interval, the first in-range frame immediately after below-range startup can
retain that flag. With both ADC limits known, this one frame per observed
rise also receives grace within the same 10 µs window. Its intervening samples
remain ambiguous: it is excluded, counted toward the exclusion limit and in
`startup_boundary_samples` and `startup_ambiguous_s`, and stays invalid for
the power estimator. A current above-range sample is never excused.

## Optional automatic recording in the existing server

Pass `shot_recording` to `TpIntensityBufferController` or `run_server`:

```python
configuration = intensity_servo.configuration(ol)
shot_recording = {
    "directory": "/home/xilinx/jupyter_notebooks/intensity_shots",
    "decimation_log2": 6,
    "tail_s": 0.001,
    "maximum_buffer_bytes": 64 * 1024**2,
}
```

The recorder derives the selected physical scale automatically; a `power_per_code` override, if supplied, must agree. See [physical-power uploads](intensity_power_upload.md) for the 50/200 mW modes.

The recorder takes the actual `low_power`/`high_power` selection, calibration
hashes, controller coefficients and physical scale from the configured Overlay.
It also saves the RFDC mixers, detector phase correction and LO amplitude, and
rejects changed settings during a shot. An active intensity FRA tone or capture
must be stopped before arming an experimental shot.

For the command-line server, save the dictionary as JSON and supply
`--shot-recording-json path/to/recording.json`. Without this option the existing
server behavior is retained. The `wait_done` reply contains the saved path,
sample count, quality status and reference key. The host worker saves that
reply in `/results/tp_intensity_streamer` of the experimental HDF5 shot file.
The actual NPZ remains on the RFSoC until copied; it is not silently transferred
over ZMQ or embedded in the host HDF5.

When the server owns a fresh attach-only Overlay, the calibration hashes from
another notebook are not present in that Python object. Supply
`shot_recording['servo_configuration'] = intensity_servo.configuration(ol)`
from the configured notebook before starting that server. The recorder checks
all current registers and the control word against the saved snapshot before
reattaching its provenance. LUT contents cannot be read back; this is only
appropriate for the same uninterrupted bitstream/table-loading session.
Using `TpIntensityBufferController(overlay=ol, shot_recording=...)` in the same
process already retains that metadata and needs no reattachment.

## Controller optimization from repeated experimental shots

`intensity_shot_analysis.shot_metrics(record)` uses the calibrated optical RMS
tracking error as the **only optimization cost**:

\[
J=\sqrt{\frac{1}{N}\sum_{n\in\mathrm{valid,\ illuminated}}
             [P_{\rm ref}(n)-P_{\rm measured}(n)]^2}.
\]

`score` and `error_rms_power` both equal this RMS in the record's physical
power units (normally mW). A valid but slower rise can only be assessed once
its power enters the calibrated sensor range. The explicit startup exclusion
limits above reject excessive missing data; there is no fabricated startup
power and no weighted penalty hidden in `score`. Normalized RMS, overshoot,
actuator range, excluded fraction and an error-spectrum ringing peak are
reported separately.
A narrow peak is a diagnostic, not proof of a self-excited instability: an
external disturbance can produce the same feature.

`next_controller_trial` implements a deliberately small coordinate search. It
varies one nonzero parameter at a time (10% function default; the notebook
explicitly uses 0.5%), inside bounds supplied by the
measured-plant stability analysis, and requests at least two repeated shots
per candidate. It compares only shots with identical sampled reference and
calibration identity. Clipped, incomplete or invalid candidates are rejected;
an invalid baseline stops the search. Candidate cost is the RMS of the
repeated shots' RMS errors, still in mW; repeated-shot scatter is reported
separately and is not added to that cost. Do not mix the older normalized,
penalized scores with this version: begin a new trial list.

The function recommends the next parameter dictionary; it neither launches an
experiment nor writes hardware. Keep controller order, sensor mode, feedforward
and incident-power adaptation fixed during a search round. Only after accepting
a candidate, start another round around it, normally with a smaller step.
Bounds around a known stable controller are necessary: tracking error alone
does not measure phase margin or guarantee >500 kHz feedback bandwidth.

## Bayesian estimate of effective incident power

On a settled, illuminated plateau the calibrated model is

\[
P_{\rm measured}=A F(u),\qquad
z=\log(P_{\rm measured}/F(u))=\log A+\text{noise}.
\]

`incident_power_observation` uses the measured actuator command, optional
actuator-to-detector delay, and the calibrated AOM transmission. It excludes
ramps, recent setpoint changes, clipping, out-of-range sensor/actuator values,
near-zero transmission and excessive tracking error. It needs at least three
complete stationary blocks. Choose the block duration longer than the residual
noise correlation time. The default is 1 ms blocks, a 100 µs settling guard,
3% tracking-error limit, and a 1% observation uncertainty floor. At very low
transmission the default 3% transmission floor may preclude updates; lower it
only after checking measured detector SNR.

`update_power_estimate` is a scalar Bayesian/Kalman update for log power. Its
prior spreads with elapsed time according to a slow random-walk drift model;
large unexplained jumps are rejected. It does not treat millions of correlated
ADC samples as independent measurements. The AOM/sensor systematic uncertainty
is stored separately and bounds the posterior from below: even infinitely many
identical shots cannot reduce the nominal 1% model/calibration floor. Increase
that floor when the sensor calibration uncertainty exceeds it. This is a
conservative bounded scalar filter, not a claim of independent calibration
errors on successive shots. Reset/revalidate the prior after
changing calibration, optical collection or detector attenuation.

Because `F` is relative, the result is **effective input power times fixed
collection/normalization factors**, not an absolute AOM-input power meter.
Sensor gain changes, beam alignment changes and true incident-power changes are
not separately identifiable from these measurements alone.

The resulting inverse-power correction belongs **once** in the shared virtual
actuator path, after feedforward plus feedback and before the AOM inverse map.
That changes their effective overall gain together. Do not additionally divide
the PI/PII/PIII coefficients by the same estimate. `gain_scale_recommendation`
limits each accepted between-shot correction to 5% by default, with absolute
limits around the validated operating point. Freeze this adaptation while
optimizing controller parameters, and apply changes only between finished
shots; never while a command DMA is armed or running.

The present 300 kHz model has only about 0.170 dB gain margin despite a much
larger local phase margin. That does not support unattended gain optimization:
5% gain is already 0.42 dB. The example therefore limits changes to 0.5% and
requires a new measured FRA to establish adequate margin first. This small
step is not itself a stability guarantee, especially with at least 1% model
uncertainty or multiple updates accumulating in the same direction.

After accepting controller parameters, automatic adaptation can be enabled:

```python
import intensity_servo
import intensity_shots

configuration = intensity_servo.configuration(ol)
optimized_shots_and_new_fra_verified = False  # Set only after reviewing both.
assert optimized_shots_and_new_fra_verified
shot_recording["adapt_incident_power"] = {
    "optimizer_certified": True,
    "controller_signature": intensity_shots.controller_signature(configuration),
    "state_path": "/home/xilinx/jupyter_notebooks/intensity_shots/power_state.json",
    "nominal_power_mW": configuration["effective_power_mW"],
    "maximum_step_fraction": 0.005,
    "allowed_power_ratio": [0.5, 2.0],
    "observation": {"block_s": 0.001, "settle_s": 0.0001},
}
```

The signature fixes the optimized controller, feedforward selection, detector
mode and calibration while allowing the intended inverse-power scale to vary.
Changing these fixed settings makes automatic adaptation stop with an explicit
reason. The persistent prior is likewise tied to that identity and units.

The automatic path requires a complete capture, no configuration changes
during the shot, idle command/receive DMAs, and a final 100 µs interval with
both reference and actual actuator zero. A nonzero manual reference prevents
adaptation. For a serial shot ending at zero, the software temporarily selects
an explicit manual zero, calls the guarded power-update helper, then restores
the original selector and manual shadow value. The helper disables/resets the
new controller while its coefficients change; this is an intentionally dark
between-shot operation, not a live bumpless change.

Each attempt writes `shot_name.adaptation.json` containing the prior/observation,
accepted estimate and settings before/after, or a reason for skipping. The
measurement NPZ remains the pre-update record. Invalid observations preserve
the previous applied scale. The prior state is saved atomically after the
attempt. Both the shared gain step and effective-power step are limited; no
controller coefficients are independently rescaled.

## Register map and RTL guide

`intensity_shot_control` GPIO channel 1 contains arm bit 0, decimation exponent
bits 5:1, and maximum frame count bits 31:8. Its input channel reports the
produced count in bits 31:8 and waiting/running/done/overflow/truncated/invalid/
configuration-changed in bits 0 through 6. `intensity_shot_tail` channel 1 is
the tail duration in FPGA clocks; channel 2 is signature `0x49533031` (IS01).

The logger's validity check uses filtered ADC validity. The existing continuous
DAC stream does not supply a meaningful stall monitor to this recorder (the
older diagnostic path's DAC-ready input is tied high as well). A successful
capture does not prove that RFDC startup, output clocking or analog DAC output
are correct; verify those with the normal initialization and hardware checks.

In `intensity_shot_capture.sv`, the declarations define WAIT/RUN/FINISH/DONE,
saved settings and the one-frame holdback. The `frame` wire implements the four
words above. The reset branch clears only the monitor. WAIT snapshots settings
and starts on a streamer edge. RUN accumulates fault flags, counts tail clocks
and periodically moves the pending frame into the AXI register before sampling
the next frame. Busy AXI output drops a monitor sample and latches overflow.
The finite maximum sets truncated. FINISH releases the held frame with TLAST;
DONE is asserted only after its AXI handshake. The wrapper adds Vivado's clock
and AXI interface inference without additional logic.
