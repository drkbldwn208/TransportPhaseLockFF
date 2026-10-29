"""RFSoC TP intensity DMA buffer controller.

This file is intended to run on the RFSoC/PYNQ side.

It owns the PYNQ overlay handle, a persistent uint32 DMA buffer, and the
``axi_dma_6`` MM2S channel that feeds ``dwell_fcw_streamer_32_0``.

The controller is deliberately independent of ZMQ so it can also be imported
from a Jupyter notebook for direct testing.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np


def _check_power_range(words, configuration):
    """Check sensor coverage and available AOM power, including command rounding."""
    required = ('sensor_power_limits_mW', 'effective_power_mW',
                'maximum_transmission_fraction', 'power_per_code',
                'sensor_calibration_sha256', 'aom_calibration_sha256')
    if any(configuration.get(key) is None for key in required):
        raise ValueError('Attach loaded calibration and incident-power provenance before a calibrated shot.')
    mode = 'high_power' if configuration['control_word'] & 8 else 'low_power'
    lower, upper = configuration['sensor_power_limits_mW'][mode]
    upper = min(upper, configuration['effective_power_mW'] *
                configuration['maximum_transmission_fraction'])
    references = (words >> 16).astype(float) * configuration['power_per_code']
    nonzero = references[references != 0]
    if np.any((nonzero < lower) | (nonzero > upper)):
        raise ValueError(f'Shot reference must be zero/off or inside [{lower:g}, {upper:g}] mW '
                         f'for {mode}; check units and available AOM power.')


class TpIntensityBufferController:
    """Load TP intensity streamer words into a reusable PYNQ DMA buffer."""

    def __init__(
        self,
        *,
        bitfile=None,
        overlay=None,
        max_words=1_000_000,
        download_overlay=False,
        set_serial_mode=True,
        shot_recording=None,
        servo_configuration=None,
    ):
        if overlay is None:
            if bitfile is None:
                raise ValueError("Provide either bitfile or an existing PYNQ overlay object")
            from pynq import Overlay

            print("TP buffer: attaching overlay", flush=True)
            overlay = Overlay(bitfile, download=download_overlay)

        from pynq import allocate

        print(f"TP buffer: allocating {int(max_words)} uint32 words", flush=True)
        self.overlay = overlay
        self.dma = overlay.axi_dma_6
        self.buffer = allocate(shape=(int(max_words),), dtype=np.uint32)
        self.max_words = int(max_words)
        self.loaded_words = 0
        self.loaded_metadata = {}
        # Opt-in monitor. Existing shot playback is unchanged when None.
        self.shot_recording = None if shot_recording is None else dict(shot_recording)
        self._shot_capture = None
        self._shot_path = None
        self._last_shot_record = None
        self._shot_power_per_code = 1.
        if servo_configuration is not None:
            from intensity_shots import attach_saved_configuration
            attach_saved_configuration(overlay, servo_configuration)
        if self.shot_recording is not None:
            import intensity_shots
            intensity_shots.check(overlay)
            if 'directory' not in self.shot_recording:
                raise ValueError('shot_recording requires an output directory on the RFSoC.')
            if 'servo_configuration' in self.shot_recording:
                intensity_shots.attach_saved_configuration(overlay, self.shot_recording['servo_configuration'])

        print("TP buffer: resetting axi_dma_6 sendchannel", flush=True)
        self.reset()

        if set_serial_mode:
            print("TP buffer: selecting serial setpoint path", flush=True)
            self.select_serial_setpoint()
        print("TP buffer: ready", flush=True)

    def select_serial_setpoint(self):
        """Make setpoint_switch select dwell-streamer output.

        In setpoint_switch.v:

            sw_toggle=0 -> serial_setpoint
            sw_toggle=1 -> gpio_setpoint
        """

        self.overlay.axi_gpio_11.channel1.write(0, mask=0xFFFF)

    def select_gpio_setpoint(self):
        """Return setpoint_switch to manual GPIO setpoint mode."""

        self.overlay.axi_gpio_11.channel1.write(1, mask=0xFFFF)

    def dma_idle(self):
        return bool(self.dma.sendchannel.idle)

    def load_power_and_arm(self, time_s, power_mW, *, sensor_mode, metadata=None):
        """Convert physical power before the shot; FPGA timing still uses the trigger.

        The selected sensor table must match the declared physical attenuation.
        This method never switches attenuation or changes controller settings.
        """
        import intensity_servo as servo
        configuration = servo.configuration(self.overlay)
        control = configuration['control_word']
        if not control & 1:
            raise ValueError('Enable the calibrated intensity path before uploading mW commands.')
        selected = 'high_power' if control & 8 else 'low_power'
        if sensor_mode not in ('low_power', 'high_power') or sensor_mode != selected:
            raise ValueError(f'Declared attenuation {sensor_mode!r} does not match selected {selected} table.')
        if configuration.get('sensor_mode') != selected:
            raise ValueError('Use configure_controller() to switch sensor mode and output scaling together.')
        scale = configuration.get('power_full_scale_mW')
        if scale is None:
            raise ValueError('Attach the loaded servo calibration snapshot before uploading mW commands.')
        t = np.asarray(time_s, dtype=float)
        power = np.asarray(power_mW, dtype=float)
        if (t.ndim != 1 or t.shape != power.shape or len(t) < 2 or
                not np.isfinite(t).all() or t[0] != 0 or np.any(np.diff(t) <= 0)):
            raise ValueError('Use paired power/time arrays, starting at trigger-relative t=0, strictly increasing.')
        # Bound expansion before allocating commands for long dwell intervals.
        clocks = np.diff(np.rint(t*servo.FS_HZ))
        if np.any(clocks < 1) or np.sum(np.ceil(clocks/65536)) + 1 > self.max_words:
            raise ValueError('Waveform has sub-clock holds or exceeds max_words after dwell expansion.')
        words = servo.waveform_words(t, power, power_full_scale_mW=scale)
        if np.any((power[:-1] > 0) & (np.rint(power[:-1]*65536/scale) == 0)):
            raise ValueError('A nonzero requested power rounds to the reserved off code.')
        info = dict(metadata or {})
        info.update(command_units='power_codes', source_power_units='mW',
                    sensor_mode=selected, power_full_scale_mW=float(scale),
                    duration_s=float(t[-1]), num_power_points=len(t))
        reply = self.load_and_arm(words, metadata=info)
        reply.update(sensor_mode=selected, power_full_scale_mW=float(scale),
                     power_per_code_mW=float(scale)/65536)
        return reply

    def load_and_arm(self, words, metadata=None):
        """Copy words into the DMA buffer, flush, and start MM2S.

        Starting MM2S does not start the physical ramp immediately. The DMA
        will present data to the HLS streamer, but the streamer remains idle
        until its hardware start input receives the trigger pulse.
        """

        words = np.asarray(words, dtype=np.uint32)
        n_words = int(words.size)
        print(f"TP buffer: load_and_arm requested for {n_words} words", flush=True)
        if n_words <= 0:
            raise ValueError("empty TP intensity command array")
        if n_words > self.max_words:
            raise ValueError(f"{n_words} words received, max_words={self.max_words}")
        if not self.dma_idle():
            raise RuntimeError("axi_dma_6 sendchannel is busy")
        if self._shot_capture is not None:
            raise RuntimeError('Finish/save the preceding shot capture before arming another shot.')

        metadata = dict(metadata or {})
        if 'intensity_servo_control' in self.overlay.ip_dict:
            import intensity_servo
            configuration = intensity_servo.configuration(self.overlay)
            calibrated = bool(configuration['control_word'] & 1)
            if calibrated and metadata.get('command_units') != 'power_codes':
                raise ValueError('Calibrated path requires explicit command_units=power_codes; '
                                 'old ADC-count waveforms are not optical power. Prefer load_power_and_arm().')
            if not calibrated and metadata.get('command_units') == 'power_codes':
                raise ValueError('Power-code commands require the calibrated path, not the legacy ADC-count PI.')
            if calibrated:
                mode = 'high_power' if configuration['control_word'] & 8 else 'low_power'
                if configuration.get('sensor_mode') != mode:
                    raise ValueError('Sensor mode and host scaling disagree; reconfigure between shots.')
                if (metadata.get('sensor_mode', mode) != mode or
                        metadata.get('power_full_scale_mW', configuration['power_full_scale_mW']) !=
                        configuration['power_full_scale_mW']):
                    raise ValueError('Packed waveform was encoded for a different mode/full scale.')
                _check_power_range(words, configuration)
                metadata['servo_configuration_start'] = configuration
        if ('intensity_control' in self.overlay.ip_dict and
                self.overlay.intensity_control.read(0) & 3):
            raise RuntimeError('Stop the intensity FRA tone/capture before arming an experimental shot.')

        self.buffer[:n_words] = words
        self.buffer.flush()
        print("TP buffer: DMA buffer copied and flushed", flush=True)

        self.loaded_metadata = metadata
        if self.shot_recording is not None:
            import intensity_shots
            import intensity_calibration
            options = self.shot_recording
            if ('intensity_control' in self.overlay.ip_dict and
                    self.overlay.intensity_control.read(0) & 3):
                raise RuntimeError('Stop the intensity FRA tone/capture before arming an experimental shot.')
            operating = intensity_calibration.configuration(self.overlay)
            configuration = operating['linearized_servo']
            self.loaded_metadata['operating_configuration_start'] = operating
            self.loaded_metadata['servo_configuration_start'] = configuration
            for name in ('power_units', 'sensor_mode', 'sensor_calibration_sha256', 'aom_calibration_sha256', 'rf_chain'):
                self.loaded_metadata[name] = configuration.get(name)
            self._shot_power_per_code = float(configuration.get('power_per_code', options.get('power_per_code', 1.)))
            if ('power_per_code' in options and
                    not np.isclose(float(options['power_per_code']), self._shot_power_per_code, rtol=1e-9)):
                raise ValueError('Recording power scale disagrees with the loaded calibration metadata.')
            if configuration.get('control_word', 0) & 1:
                _check_power_range(words, configuration)
            # Sum encoded dwell lengths; do not depend on host wall-clock timing.
            duration_s = float(np.sum((words.astype(np.uint64) & 65535)+1))/245.76e6
            plan = intensity_shots.capture_plan(
                duration_s, decimation_log2=int(options.get('decimation_log2', 6)),
                tail_s=float(options.get('tail_s', .001)),
                maximum_buffer_bytes=int(options.get('maximum_buffer_bytes', 64*1024**2)))
            directory = Path(options['directory']).expanduser()
            stem = Path(self.loaded_metadata.get('h5_path', 'intensity_shot')).stem
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
            self._shot_path = directory / f'{stem}_{stamp}_{uuid4().hex[:8]}.npz'
            self._shot_capture = intensity_shots.arm(
                self.overlay, maximum_samples=plan['maximum_samples'],
                decimation_log2=plan['decimation_log2'], tail_s=plan['tail_s'])
            self.loaded_metadata['capture_plan'] = plan
        t0 = time.perf_counter()
        try:
            # Receive capture is already armed before the streamer sees commands.
            self.dma.sendchannel.transfer(self.buffer[:n_words])
        except BaseException:
            if self._shot_capture is not None:
                import intensity_shots
                intensity_shots.cancel(self.overlay, self._shot_capture)
                self._shot_capture = None
            raise
        arm_time_ms = 1e3 * (time.perf_counter() - t0)
        print(f"TP buffer: axi_dma_6 MM2S armed in {arm_time_ms:.3f} ms", flush=True)

        self.loaded_words = n_words
        return {
            "status": "ok",
            "message": "tp intensity DMA armed",
            "num_words": n_words,
            "num_bytes": int(n_words * 4),
            "arm_time_ms": arm_time_ms,
        }

    def wait_done(self, timeout_s=5.0, poll_s=0.005):
        """Wait for the physical shot record, or MM2S completion without recording.

        With recording enabled, the logger observes the streamer's active signal
        and waits through the final dwell and capture tail. MM2S idle alone only
        means all commands were delivered; buffering can precede physical shot
        completion. The legacy mode retains that weaker completion condition.
        """

        start = time.perf_counter()
        timeout_s = float(timeout_s)
        print(f"TP buffer: wait_done timeout_s={timeout_s}", flush=True)
        if self._shot_capture is not None:
            import intensity_shots
            options = self.shot_recording
            metadata = dict(options.get('metadata', {}))
            metadata.update(self.loaded_metadata)
            try:
                self._last_shot_record = intensity_shots.finish(
                    self.overlay, self._shot_capture, path=self._shot_path,
                    metadata=metadata, timeout_s=timeout_s,
                    power_per_code=self._shot_power_per_code)
            finally:
                self._shot_capture = None
            if not self.dma_idle():
                raise RuntimeError('Shot capture ended while command DMA is still busy; inspect '+self._last_shot_record['path'])
            if options.get('adapt_incident_power'):
                adaptation = intensity_shots.adapt_after_shot(
                    self.overlay, self._last_shot_record['path'], options['adapt_incident_power'])
                self._last_shot_record['adaptation'] = {
                    'applied': adaptation['applied'], 'reason': adaptation['reason']}
            return dict(status='ok', done=True, elapsed_s=time.perf_counter()-start,
                        loaded_words=int(self.loaded_words), shot_record=self._last_shot_record)
        while True:
            if self.dma_idle():
                elapsed_s = time.perf_counter() - start
                print(f"TP buffer: DMA done after {elapsed_s:.6f} s", flush=True)
                return {
                    "status": "ok",
                    "done": True,
                    "elapsed_s": elapsed_s,
                    "loaded_words": int(self.loaded_words),
                }
            if time.perf_counter() - start > timeout_s:
                elapsed_s = time.perf_counter() - start
                print(f"TP buffer: wait_done timed out after {elapsed_s:.6f} s", flush=True)
                return {
                    "status": "timeout",
                    "done": False,
                    "elapsed_s": elapsed_s,
                    "loaded_words": int(self.loaded_words),
                }
            time.sleep(float(poll_s))

    def status(self):
        return {
            "status": "ok",
            "loaded_words": int(self.loaded_words),
            "dma_idle": self.dma_idle(),
            "metadata": self.loaded_metadata,
            "shot_capture_armed": self._shot_capture is not None,
            "last_shot_record": self._last_shot_record,
        }

    def reset(self):
        """Force-stop a stuck MM2S transfer and return the channel to idle."""

        print("TP buffer: stopping axi_dma_6 sendchannel", flush=True)
        self.dma.sendchannel.stop()
        if self._shot_capture is not None:
            import intensity_shots
            intensity_shots.cancel(self.overlay, self._shot_capture)
            self._shot_capture = None
        # PYNQ transfer() requires a running channel. Starting an empty channel
        # only returns it to idle; it does not send commands or trigger a ramp.
        self.dma.sendchannel.start()
        self.loaded_words = 0
        self.loaded_metadata = {}
        reply = {
            "status": "ok",
            "message": "axi_dma_6 sendchannel reset",
            "dma_idle": self.dma_idle(),
        }
        print(f"TP buffer: reset reply={reply}", flush=True)
        return reply
