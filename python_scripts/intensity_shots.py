"""Triggered per-shot intensity records through the dedicated IS01 receive DMA.

Arm receive before command MM2S. Hardware starts on streamer active rising and
finishes after its falling edge plus tail. No Python timing sets the waveform.
The monitor is independent of the existing calibration/FRA DMA.
"""

import time
import hashlib
import json
from pathlib import Path

import numpy as np

import intensity_shot_analysis as analysis

FS_HZ = 245.76e6
FEATURE_VERSION = 0x49533031
DMA_MAX_BYTES = (1 << 26)-1


def controller_signature(configuration):
    """Identity of optimized controller/calibration, excluding intended power drift.

    Dynamic status, configuration epoch, and inverse incident-power scale are
    excluded. Controller order, feedforward selection, gains, range limits,
    detector mode, calibration identities and physical units remain included.
    """
    registers = {name: value for name, value in configuration['registers'].items()
                 if name not in ('inverse_power_scale_q20', 'configuration_epoch')}
    identity = dict(control_word=configuration['control_word'] & ~(1 << 6), registers=registers)
    for name in ('feature_version', 'sensor_calibration_sha256', 'aom_calibration_sha256',
                 'power_units', 'power_per_code', 'power_full_scale_mW', 'sensor_mode', 'rf_chain'):
        identity[name] = configuration.get(name)
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def attach_saved_configuration(ol, saved):
    """Restore host provenance on an attach-only Overlay after register checks.

    This writes no FPGA registers. LUT contents have no readback, so the user
    must supply a snapshot from the same uninterrupted table-loading session;
    matching register counts alone do not prove matching calibration contents.
    """
    import intensity_servo
    actual = intensity_servo.configuration(ol)
    if (actual['registers'] != saved['registers'] or actual['control_word'] != saved['control_word']
            or actual.get('rf_chain') != saved.get('rf_chain')):
        raise ValueError('Saved servo configuration does not match current registers.')
    required = ('sensor_calibration_sha256', 'aom_calibration_sha256', 'power_units',
                'power_full_scale_mW', 'power_per_code', 'effective_power_mW')
    if any(saved.get(key) is None for key in required):
        raise ValueError('Saved servo snapshot lacks calibration/power provenance.')
    ol._intensity_servo_metadata = {key: value for key, value in saved.items()
                                  if key not in ('registers', 'control_word', 'status', 'feature_version', 'rf_chain')}


def check(ol):
    for name in ('intensity_shot_control', 'intensity_shot_tail', 'intensity_shot_dma'):
        if name not in ol.ip_dict:
            raise ValueError(f'Missing {name}; this bitstream does not contain the shot logger.')
    if ol.intensity_shot_tail.read(8) != FEATURE_VERSION:
        raise ValueError('Shot logger feature signature mismatch.')


def capture_plan(duration_s, *, decimation_log2=6, tail_s=.001,
                 maximum_buffer_bytes=64*1024**2):
    """Reserve the full shot at fixed sample rate; never silently downsample.

    D=6: 3.84 MS/s, 61.44 MB/s, Nyquist 1.92 MHz. The hardware takes point
    samples, not averages; it adds no servo latency. Existing input filtering
    does not make arbitrary additional decimation alias-free.
    """
    if not np.isfinite([duration_s, tail_s]).all() or duration_s <= 0 or tail_s < 0:
        raise ValueError('Use a positive shot duration and nonnegative tail.')
    if not isinstance(decimation_log2, int) or not 3 <= decimation_log2 <= 24:
        raise ValueError('decimation_log2 must be an integer from 3 to 24.')
    fs_hz = FS_HZ/2**decimation_log2
    # Include guard samples for trigger/word boundary clocks. The hardware
    # still emits TLAST at actual shot end; allocation does not extend capture.
    samples = int(np.ceil((duration_s+tail_s)*fs_hz))+16
    if samples >= 2**24 or samples*16 > min(maximum_buffer_bytes, DMA_MAX_BYTES):
        raise ValueError(f'Shot needs {samples*16/1024**2:.1f} MiB. Increase D explicitly '
                         'or choose a shorter/high-rate diagnostic shot; receive DMA length is limited to 26 bits.')
    return dict(maximum_samples=samples, decimation_log2=decimation_log2,
                sample_rate_hz=fs_hz, tail_s=float(tail_s), buffer_bytes=samples*16)


def arm(ol, *, maximum_samples, decimation_log2=6, tail_s=.001):
    """Prepare S2MM and wait for the next physical streamer rising edge."""
    check(ol)
    if not isinstance(maximum_samples, int) or not 1 <= maximum_samples < 2**24:
        raise ValueError('maximum_samples must be in [1, 2**24-1].')
    if not isinstance(decimation_log2, int) or not 3 <= decimation_log2 <= 24:
        raise ValueError('decimation_log2 must be in [3,24].')
    tail_clocks = round(float(tail_s)*FS_HZ)
    if not 0 <= tail_clocks <= 0xffffffff:
        raise ValueError('Tail must fit a uint32 count of 245.76 MHz clocks.')
    control = ol.intensity_shot_control
    if control.read(0) & 1:
        raise RuntimeError('A shot capture is already armed; finish or cancel it first.')
    dma = ol.intensity_shot_dma
    channel_limit = getattr(dma.recvchannel, '_max_size',
                            getattr(dma.recvchannel, 'max_size', DMA_MAX_BYTES))
    if maximum_samples*16 > min(DMA_MAX_BYTES, int(channel_limit)):
        raise ValueError('Requested shot buffer exceeds the receive DMA byte-length limit.')
    from pynq import allocate
    buffer = allocate(shape=(maximum_samples, 4), dtype=np.uint32)
    try:
        if not dma.recvchannel.running:
            dma.recvchannel.start()
        dma.recvchannel.transfer(buffer)
        ol.intensity_shot_tail.write(0, tail_clocks)
        control.write(0, (maximum_samples << 8) | (decimation_log2 << 1) | 1)
    except BaseException:
        dma.recvchannel.stop()
        control.write(0, 0)
        buffer.freebuffer()
        raise
    return dict(buffer=buffer, maximum_samples=maximum_samples,
                decimation_log2=decimation_log2, tail_clocks=tail_clocks,
                sample_rate_hz=FS_HZ/2**decimation_log2, finished=False)


def cancel(ol, armed):
    """Abort only the monitor and free its buffer; the actuator is untouched."""
    if armed is None or armed.get('finished', False):
        return
    ol.intensity_shot_dma.recvchannel.stop()
    ol.intensity_shot_control.write(0, 0)
    armed['buffer'].freebuffer()
    armed['finished'] = True


def unpack(raw, *, sample_rate_hz, status, power_per_code=1., sensor_adc_limits=None):
    """Physical units use power_per_code; default values remain power counts."""
    words = np.asarray(raw, dtype=np.uint32)
    if words.ndim != 2 or words.shape[1] != 4:
        raise ValueError('Shot frames must have shape (samples,4), dtype uint32.')
    flags = (words[:, 3] & 65535).astype(np.uint16)
    error = words[:, 0].copy().view(np.int32).astype(float)/256
    reference = (words[:, 1] & 65535).astype(float)
    measured = (words[:, 1] >> 16).astype(float)
    actuator = (words[:, 2] & 65535).astype(float)
    raw_adc = (words[:, 2] >> 16).astype(np.uint16).view(np.int16)
    # Any diagnostic fault rejects optimization/estimation. The original words
    # and flags remain available for diagnosis, including an overflowed record.
    global_fault = bool(int(status) & 0x78)
    # A sensor-range warning during intentional optical-off is preserved in raw
    # flags but does not invalidate the illuminated portions of the shot. No
    # calibrated optical power is inferred for those off samples.
    usable_flags = (flags==0) | ((reference==0) & (flags==2))
    record = dict(raw=words, time_s=np.arange(len(words))/sample_rate_hz,
                reference_power=reference*power_per_code, measured_power=measured*power_per_code,
                error_power=error*power_per_code, actuator_codes=actuator,
                raw_adc_counts=raw_adc, sample_flags=flags,
                valid=usable_flags & ~np.full(len(words), global_fault),
                clipped=(flags & 5)!=0,
                complete=bool(status & 4) and not global_fault,
                status=int(status), sample_rate_hz=float(sample_rate_hz))
    if sensor_adc_limits is not None:
        record['sensor_adc_min_counts'] = int(sensor_adc_limits[0])
        record['sensor_adc_max_counts'] = int(sensor_adc_limits[1])
    return record


def finish(ol, armed, *, path, metadata=None, timeout_s=5., power_per_code=1.):
    """Wait for actual shot end, save the received frames, and release DMA memory.

    Completed faulty/truncated records are saved with complete=False for
    diagnosis. Timeout/DMA faults raise and release the monitor without touching
    the command MM2S channel or feedback controller.
    """
    if armed.get('finished', False):
        raise RuntimeError('Shot capture has already been finished/cancelled.')
    dma = ol.intensity_shot_dma
    deadline = time.monotonic()+float(timeout_s)
    try:
        while True:
            status = ol.intensity_shot_control.read(8)
            if dma.mmio.read(0x34) & 0x70:
                raise RuntimeError('Shot receive DMA error.')
            if status & 4 and dma.recvchannel.idle:
                break
            if time.monotonic() > deadline:
                raise TimeoutError('Shot logger did not complete; check hardware trigger and shot duration.')
            time.sleep(.001)
        dma.recvchannel.wait()
        samples = status >> 8
        if samples < 1 or samples > armed['maximum_samples']:
            raise RuntimeError('Shot frame count is invalid.')
        if dma.recvchannel.transferred != samples*16:
            raise RuntimeError('Shot DMA byte count does not match hardware frame count.')
        start_configuration = (metadata or {}).get('servo_configuration_start')
        sensor_adc_limits = None
        if start_configuration is not None:
            register = 'high_adc_range' if start_configuration['control_word'] & 8 else 'low_adc_range'
            limits = start_configuration['registers'][register]
            sensor_adc_limits = (limits & 65535, limits >> 16)
        record = unpack(np.array(armed['buffer'][:samples]), sample_rate_hz=armed['sample_rate_hz'],
                        status=status, power_per_code=power_per_code, sensor_adc_limits=sensor_adc_limits)
        saved_metadata = dict(metadata or {})
        if 'operating_configuration_start' in saved_metadata:
            import intensity_calibration
            end_operating = intensity_calibration.configuration(ol)
            saved_metadata['operating_configuration_end'] = end_operating
            if end_operating != saved_metadata['operating_configuration_start']:
                record['complete'] = False
        if 'servo_configuration_start' in saved_metadata:
            import intensity_servo
            end_configuration = intensity_servo.configuration(ol)
            start_configuration = saved_metadata['servo_configuration_start']
            saved_metadata['servo_configuration_end'] = end_configuration
            unchanged = (controller_signature(start_configuration) == controller_signature(end_configuration)
                         and start_configuration['registers'] == end_configuration['registers'])
            saved_metadata['servo_configuration_unchanged'] = bool(unchanged)
            if not unchanged:
                record['complete'] = False
        saved_metadata.update(feature_version=FEATURE_VERSION,
                              decimation_log2=armed['decimation_log2'],
                              tail_clocks=armed['tail_clocks'],
                              power_per_code=float(power_per_code),
                              sample_flags_meaning='bit0 actuator clip; bit1 sensor range; bit2 controller saturation; bit3 ADC invalid; bit4 legacy mode; bit5 configuration update',
                              capture_start='streamer active rising',
                              capture_end='streamer active falling plus programmed tail')
        saved_metadata = analysis.save_record(path, record, saved_metadata)
        return dict(path=str(Path(path).resolve()), samples=samples, status=int(status),
                    complete=record['complete'], reference_key=saved_metadata['reference_key'])
    finally:
        cancel(ol, armed)


def adapt_after_shot(ol, path, options):
    """Opt-in Bayesian correction after a certified controller's completed shot.

    Writes only the common incident-power factor, via intensity_servo's guarded
    between-shot helper. It never tunes controller coefficients. The experiment
    must end at zero reference. Sidecar JSON records the estimate and settings
    before/after; the NPZ remains the exact pre-update measurement.
    """
    import intensity_servo
    path = Path(path)
    with np.load(path, allow_pickle=False) as saved:
        record = {key: saved[key] for key in saved.files if key != 'metadata_json'}
        metadata = json.loads(str(saved['metadata_json']))
    before = intensity_servo.configuration(ol)
    result = dict(applied=False, before=before, shot_file=str(path.resolve()))

    def finish_result(reason):
        result['reason'] = reason
        path.with_suffix('.adaptation.json').write_text(json.dumps(result, indent=2)+'\n')
        return result

    if options.get('optimizer_certified') is not True:
        return finish_result('Adaptation disabled until controller optimization is explicitly certified.')
    signature = controller_signature(before)
    if options.get('controller_signature') != signature:
        return finish_result('Controller/calibration differs from the certified configuration.')
    if before.get('power_units') != 'mW' or not all(before.get(k) for k in
                ('sensor_calibration_sha256', 'aom_calibration_sha256', 'power_full_scale_mW', 'rf_chain')):
        return finish_result('Physical calibration provenance is unavailable.')
    start = metadata.get('servo_configuration_start')
    if start is None or controller_signature(start) != signature or not bool(record['complete']):
        return finish_result('Shot was incomplete or did not use the certified configuration.')
    if np.any(np.asarray(record.get('sample_flags', 0), np.uint16) & 0x30):
        return finish_result('Controller mode/configuration changed during the shot.')
    if start['registers']['inverse_power_scale_q20'] != before['registers']['inverse_power_scale_q20']:
        return finish_result('Incident-power factor changed after this shot; refusing a stale update.')
    if ol.intensity_shot_control.read(0) & 1 or not ol.axi_dma_6.sendchannel.idle:
        return finish_result('A capture or command DMA is still armed/running.')
    live_status = intensity_servo.status(ol)
    if live_status['shot_active'] or not live_status['active']:
        return finish_result('Require an idle shot and enabled calibrated controller.')
    reference = record['reference_power']
    final_samples = max(1, min(len(reference), round(1e-4*float(record['sample_rate_hz']))))
    if np.any(reference[-final_samples:] != 0) or np.any(record['actuator_codes'][-final_samples:] != 0):
        return finish_result('Require a final zero-reference, zero-actuator interval before adaptation.')
    selector = int(ol.axi_gpio_11.read(0))
    manual = int(ol.axi_gpio_11.read(8))
    if selector & 1 and manual & 65535:
        return finish_result('Manual reference is nonzero; automatic adaptation would interrupt the beam.')
    state_path = Path(options['state_path']).expanduser()
    nominal_power = float(options['nominal_power_mW'])
    calibration_key = dict(sensor=before['sensor_calibration_sha256'],
                           aom=before['aom_calibration_sha256'], units='mW',
                           power_per_code=before['power_per_code'], controller_signature=signature)
    now = time.time()
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state['calibration_key'] != calibration_key:
            return finish_result('Saved Bayesian state belongs to a different calibration/controller.')
        prior = state['estimate']
        elapsed_s = max(0., now-state['timestamp_unix_s'])
    else:
        prior = analysis.power_prior(nominal_power, options.get('initial_uncertainty_fraction', .1))
        elapsed_s = 0.
    table = intensity_servo.aom_table(
        minimum_command_codes=options.get('minimum_command_codes', 4000),
        maximum_command_codes=int(before['maximum_measured_command_codes']),
        alpha_rad_per_code=float(before['aom_alpha_rad_per_code']))
    observation = analysis.incident_power_observation(
        record, table, **options.get('observation', {}))
    estimate = analysis.update_power_estimate(
        prior, observation, elapsed_s=elapsed_s,
        drift_fraction_per_sqrt_s=options.get('drift_fraction_per_sqrt_s', .01))
    result.update(observation=observation, estimate=estimate)
    if estimate['updated']:
        ratio_limits = options.get('allowed_power_ratio', [.5, 2.])
        full_scale = float(before['power_full_scale_mW'])
        previous_scale = before['registers']['inverse_power_scale_q20']/2**20
        recommendation = analysis.gain_scale_recommendation(
            estimate, full_scale, previous_scale=previous_scale,
            maximum_step_fraction=options.get('maximum_step_fraction', .05),
            limits=(full_scale/(nominal_power*ratio_limits[1]), full_scale/(nominal_power*ratio_limits[0])))
        result['scale_recommendation'] = recommendation
        # The shot's actual zero ending was verified above. Temporarily select
        # an explicit manual zero for the coefficient-update guard, then restore
        # serial/manual selection for the next shot. No live waveform is paused.
        ol.axi_gpio_11.write(8, 0)
        ol.axi_gpio_11.write(0, 1)
        try:
            result['update'] = intensity_servo.apply_incident_power(
                ol, full_scale/recommendation['scale'],
                maximum_step_fraction=options.get('maximum_step_fraction', .05))
        except Exception as exc:
            result['error'] = str(exc)
            finish_result('Hardware power update failed; inspect current intensity settings before the next shot.')
            raise
        finally:
            ol.axi_gpio_11.write(8, manual)
            ol.axi_gpio_11.write(0, selector)
        result.update(applied=True, after=intensity_servo.configuration(ol))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = dict(calibration_key=calibration_key, estimate=estimate, timestamp_unix_s=now)
    temporary = state_path.with_suffix(state_path.suffix+'.tmp')
    temporary.write_text(json.dumps(state, indent=2)+'\n')
    temporary.replace(state_path)
    return finish_result('Applied bounded incident-power correction.' if result['applied']
                         else 'No reliable incident-power observation; previous gain retained.')
