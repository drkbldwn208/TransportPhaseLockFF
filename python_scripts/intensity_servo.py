"""Calibrated intensity control in optical-power units.

Two ADC->power tables correct the selectable detector attenuation. A common
sin² AOM inverse converts feedforward plus feedback power into RF envelope
codes. Pure table/coefficient functions below never access hardware. Power
codes use the selected mode's full_scale_mW/65536; output-table indices are Q0.16 transmission.
"""

import csv
import fcntl
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

FS_HZ = 245.76e6
INTEGRATOR_FS_HZ = FS_HZ / 2
POWER_FULL_SCALE_MW = 200.0
AOM_ALPHA_RAD_PER_CODE = 4.721560469794474e-5
AOM_MAXIMUM_MEASURED_CODE = 21335
FAST_FEEDBACK_DELAY_S = 11 / FS_HZ
FEATURE_VERSION = 0x49530301
REGISTER_BASE = 0x20000
REGISTER_NAMES = ('kp_q12', 'alpha1_q24', 'alpha2_q24', 'alpha3_q24',
                  'leadlag_alpha_q30', 'leadlag_gain_q12', 'inverse_power_scale_q20',
                  'low_adc_range', 'high_adc_range', 'maximum_fraction_code',
                  'maximum_command_codes', 'configuration_epoch', 'low_table_count',
                  'high_table_count', 'output_table_count')


def check(ol):
    for name in ('intensity_servo_control', 'intensity_servo_write', 'intensity_servo_read'):
        if name not in ol.ip_dict:
            raise ValueError(f'Missing {name}; load the matching calibrated-servo bit/HWH.')
    if ol.intensity_servo_read.read(8) != FEATURE_VERSION:
        raise ValueError('Calibrated-servo signature mismatch; expected 0x49530301.')


def status(ol):
    check(ol)
    word = int(ol.intensity_servo_control.read(8))
    names = ('active', 'tables_ready', 'high_power_mode', 'actuator_clipped',
             'sensor_outside_range', 'controller_saturated', 'adc_valid',
             'configuration_fault', 'low_table_loaded', 'high_table_loaded',
             'output_table_loaded', 'shot_active')
    return dict(word=word, **{name: bool(word & (1 << bit)) for bit, name in enumerate(names)})


def _require_editable(ol):
    check(ol)
    if ol.intensity_servo_control.read(0) & 1 or ol.intensity_servo_control.read(8) & (1 << 11):
        raise RuntimeError('Change tables/coefficients only with new path disabled and no active shot. '
                           'Use safe_off() deliberately between shots first.')
    _require_no_shot(ol)


def _require_no_shot(ol):
    if status(ol)['shot_active']:
        raise RuntimeError('A shot is active; wait for completion.')
    if 'intensity_shot_control' in ol.ip_dict and ol.intensity_shot_control.read(0) & 1:
        raise RuntimeError('Shot capture is armed; finish/cancel it before configuration changes.')
    if 'axi_dma_6' in ol.ip_dict:
        channel = ol.axi_dma_6.sendchannel
        if channel.running and not channel.idle:
            raise RuntimeError('Command DMA is armed or running; finish the shot before configuration changes.')


def _write_words(ol, addresses, values):
    # Address/readback and write-toggle share one GPIO. Serialize even readers
    # across notebook/server processes, so a stale toggle cannot become a write.
    with open('/tmp/intensity_servo_gpio.lock', 'a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        _require_editable(ol)
        gpio = ol.intensity_servo_write
        toggle = int(gpio.read(0)) & 0x80000000
        for address, value in zip(addresses, values):
            gpio.write(8, int(value) & 0xffffffff)
            toggle ^= 0x80000000
            gpio.write(0, int(address) | toggle)


def _read_registers(ol):
    # Address selection without changing the toggle is read-only for the
    # datapath; the FPGA writes a register only when the toggle changes.
    values = {}
    with open('/tmp/intensity_servo_gpio.lock', 'a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        gpio = ol.intensity_servo_write
        toggle = int(gpio.read(0)) & 0x80000000
        for offset, name in enumerate(REGISTER_NAMES):
            gpio.write(0, (REGISTER_BASE + offset) | toggle)
            values[name] = int(ol.intensity_servo_read.read(0))
    return values


def configuration(ol):
    """Snapshot actual registers plus host-known table provenance, no gain change.

    Calibration metadata is attached to this Python Overlay object when tables
    are loaded. In a new notebook without that metadata the hashes are unknown;
    register counts alone cannot prove which calibration was loaded.
    """
    check(ol)
    result = dict(feature_version=FEATURE_VERSION,
                  control_word=int(ol.intensity_servo_control.read(0)),
                  registers=_read_registers(ol))
    result['rf_chain'] = None
    if 'usp_rf_data_converter_0' in ol.ip_dict:
        rf = ol.usp_rf_data_converter_0
        result['rf_chain'] = dict(
            adc_mixer=dict(rf.adc_tiles[0].blocks[1].MixerSettings),
            lo_mixer=dict(rf.dac_tiles[0].blocks[1].MixerSettings),
            aom_mixer=dict(rf.dac_tiles[0].blocks[3].MixerSettings),
            gpio={str(n): [int(getattr(ol, f'axi_gpio_{n}').read(a)) for a in (0, 8)]
                  for n in (9, 10, 12)},
        )
    result.update({key: value for key, value in getattr(ol, '_intensity_servo_metadata', {}).items()
                   if key not in ('control_word', 'registers', 'status', 'feature_version', 'rf_chain')})
    return result


def safe_off(ol):
    """Explicit cold/between-shot OFF: mute legacy output, disable both controllers.

    Disabling only the new path reconnects the legacy intensity output. Set
    that output to zero first so a stale legacy PI command is not selected.
    This function changes only intensity settings; it does not touch PLLs/RFDC.
    It is intentionally not a bumpless change during an illuminated shot.
    """
    check(ol)
    _require_no_shot(ol)
    if 'intensity_control' in ol.ip_dict:
        if ol.intensity_control.read(0) & 2:
            raise RuntimeError('An intensity FRA capture is armed; finish it before reconfiguration.')
        if ol.intensity_control.read(0) & 1:
            from intensity_calibration import stop
            stop(ol)
    ol.axi_gpio_9.write(8, 0)
    ol.axi_gpio_9.write(0, 1)
    ol.fast_servo_controller_0.write(0x10, 0)
    ctrl = int(ol.intensity_servo_control.read(0))
    ol.intensity_servo_control.write(0, (ctrl & ~7) | (1 << 6))


def load_calibration(ol, sensor_luts, output_lut, *, progress=True):
    """Load both sensor banks and the AOM table while the intensity output is off.

    Full sequential loads are required by hardware. Table contents have no
    readback port; completion is checked from hardware load counts and status.
    Retain the calibration files/hashes with every shot for provenance.
    """
    _require_editable(ol)
    if not ol.axi_gpio_9.read(0) & 1 or ol.axi_gpio_9.read(8) & 65535:
        raise RuntimeError('Call safe_off() before loading calibration tables.')
    sensor_values = np.asarray(sensor_luts['values'])
    output_values = np.asarray(output_lut['values'])
    if sensor_values.shape != (2, 16384) or output_values.shape != (65536,):
        raise ValueError('Expected two 16384-entry sensor tables and one 65536-entry output table.')
    for values, maximum in ((sensor_values, 65535), (output_values, 32767)):
        if (not np.issubdtype(values.dtype, np.number) or not np.isrealobj(values) or
                not np.isfinite(values).all() or np.any(values < 0) or
                np.any(values > maximum) or np.any(values != np.floor(values))):
            raise ValueError('Table entries must be finite nonnegative integers within hardware widths.')
    if (np.any(np.diff(sensor_values.astype(np.int64), axis=1) < 0) or
            np.any(np.diff(output_values.astype(np.int64)) < 0) or output_values[0] != 0 or
            np.max(output_values) > output_lut['maximum_command_codes']):
        raise ValueError('Use monotonic sensor/output tables and a zero-command output origin.')
    for label, base, values in (
        ('low-power sensor', 0x00000, sensor_values[0]),
        ('high-power sensor', 0x04000, sensor_values[1]),
        ('AOM inverse', 0x10000, output_values),
    ):
        if progress:
            print(f'Loading {label}: {len(values)} entries...', flush=True)
        _write_words(ol, range(base, base + len(values)), values)
    ranges = [int(lo) | (int(hi) << 16) for lo, hi in sensor_luts['adc_limits_counts']]
    _write_words(ol, [REGISTER_BASE + n for n in (7, 8, 9, 10)],
                 ranges + [output_lut['maximum_fraction_code'], output_lut['maximum_command_codes']])
    regs = _read_registers(ol)
    if [regs[k] for k in ('low_table_count', 'high_table_count', 'output_table_count')] != [16384, 16384, 65536]:
        raise RuntimeError('Calibration load count mismatch; leave output off and reload all tables.')
    if not status(ol)['tables_ready']:
        raise RuntimeError('Calibration tables are not ready; leave output off.')
    scales = sensor_luts.get('power_full_scale_by_mode_mW',
                            dict.fromkeys(('low_power', 'high_power'), sensor_luts['power_full_scale_mW']))
    mode = 'high_power' if ol.intensity_servo_control.read(0) & 8 else 'low_power'
    ol._intensity_servo_metadata = dict(
        power_units='mW', power_full_scale_mW=scales[mode],
        power_full_scale_by_mode_mW=dict(scales), power_per_code=scales[mode]/65536,
        sensor_mode=mode,
        sensor_calibration_sha256=sensor_luts['lut_sha256'],
        aom_calibration_sha256=output_lut['lut_sha256'],
        sensor_source_sha256=sensor_luts.get('source_sha256'),
        aom_alpha_rad_per_code=output_lut['alpha_rad_per_code'],
        minimum_measured_command_codes=output_lut['minimum_measured_command_codes'],
        maximum_measured_command_codes=output_lut['maximum_command_codes'],
        maximum_transmission_fraction=output_lut['maximum_fraction_code'] / 65536,
        sensor_power_limits_mW={
            mode: (sensor_values[bank, np.asarray(sensor_luts['adc_limits_counts'][bank])] *
                   scales[mode]/65536).tolist()
            for bank, mode in enumerate(('low_power', 'high_power'))},
    )
    if 'intensity_limits' in ol.ip_dict:
        # The diagnostic sine is added AFTER this inverse map. Give that adder
        # the same measured actuator cap so FRA cannot exceed it silently.
        ol.intensity_limits.write(0, int(output_lut['maximum_command_codes']) << 16)
    if progress:
        print('All three tables loaded; new controller remains disabled.', flush=True)
    return configuration(ol)


def configure_controller(ol, coefficients, *, sensor_mode='low_power',
                         feedforward=True, feedback=True):
    """Write/verify coefficients with the new path disabled; then call enable().

    Selecting PI/PII/PIII or changing coefficients resets controller state.
    Both modes represent mW, but may use different numerical full scales. This
    also rescales the output conversion while disabled; Kp/corners stay fixed.
    """
    _require_editable(ol)
    if sensor_mode not in ('low_power', 'high_power'):
        raise ValueError('sensor_mode must be low_power or high_power.')
    values = [coefficients['kp_q12'] & 0x3ffff] + list(coefficients['alpha_q24'])
    values += [coefficients['leadlag_alpha_q30'], coefficients['leadlag_gain_q12'] & 0x3ffff]
    _write_words(ol, range(REGISTER_BASE, REGISTER_BASE + 6), values)
    ctrl = ((bool(feedback) << 1) | (bool(feedforward) << 2) |
            ((sensor_mode == 'high_power') << 3) |
            (bool(coefficients['leadlag_enable']) << 4) |
            (int(coefficients['order']) << 7) | (1 << 6))
    ol.intensity_servo_control.write(0, ctrl)
    actual = _read_registers(ol)
    masks = [0x3ffff, 0xfffff, 0xfffff, 0xfffff, 0xffffffff, 0x3ffff]
    if any((actual[name] & mask) != value for name, value, mask in zip(REGISTER_NAMES[:6], values, masks)):
        raise RuntimeError('Controller coefficient readback mismatch; leave output off.')
    metadata = dict(getattr(ol, '_intensity_servo_metadata', {}))
    scales = metadata.get('power_full_scale_by_mode_mW')
    if scales is not None:
        metadata.update(power_full_scale_mW=scales[sensor_mode],
                        power_per_code=scales[sensor_mode]/65536)
    metadata.update(sensor_mode=sensor_mode, controller_coefficients=dict(coefficients))
    ol._intensity_servo_metadata = metadata
    if 'effective_power_mW' in metadata:
        set_incident_power(ol, metadata['effective_power_mW'])
    return configuration(ol)


def set_incident_power(ol, effective_power_mW, *, power_full_scale_mW=None):
    """Set one common inverse scale for feedforward+feedback while disabled.

    P=A_eff*F(u); the hardware multiplies desired power codes by full_scale/A_eff
    before the inverse LUT. A_eff includes collection losses and peak AOM
    efficiency. Do not apply the same reciprocal again to controller gains.
    """
    _require_editable(ol)
    metadata = dict(getattr(ol, '_intensity_servo_metadata', {}))
    if power_full_scale_mW is None:
        power_full_scale_mW = metadata.get('power_full_scale_mW')
    elif ('power_full_scale_mW' in metadata and
          power_full_scale_mW != metadata['power_full_scale_mW']):
        raise ValueError('Output scale must match the selected sensor table full scale.')
    if (power_full_scale_mW is None or not np.isfinite([effective_power_mW, power_full_scale_mW]).all() or
            min(effective_power_mW, power_full_scale_mW) <= 0):
        raise ValueError('Provide positive effective power and the calibrated common full scale in mW.')
    scale = round(power_full_scale_mW / effective_power_mW * 2**20)
    if not 1 <= scale < 2**24:
        raise ValueError('Inverse-power factor must fit unsigned Q4.20 (0 < scale < 16).')
    _write_words(ol, [REGISTER_BASE + 6], [scale])
    if _read_registers(ol)['inverse_power_scale_q20'] != scale:
        raise RuntimeError('Incident-power scale readback mismatch.')
    metadata['effective_power_mW'] = float(power_full_scale_mW / (scale/2**20))
    metadata['inverse_power_scale'] = scale/2**20
    ol._intensity_servo_metadata = metadata
    return metadata['effective_power_mW']


def enable(ol):
    """Enable the configured new path and release state reset; tables must be ready."""
    check(ol)
    _require_no_shot(ol)
    current = status(ol)
    if current['shot_active'] or not current['tables_ready']:
        raise RuntimeError('Enable between shots only, after loading all calibration tables.')
    ctrl = int(ol.intensity_servo_control.read(0))
    if (ctrl >> 7) & 3 == 0:
        raise ValueError('Configure PI, PII or PIII before enabling.')
    metadata = getattr(ol, '_intensity_servo_metadata', {})
    selected_mode = 'high_power' if ctrl & 8 else 'low_power'
    if metadata.get('sensor_mode') != selected_mode or 'effective_power_mW' not in metadata:
        raise ValueError('Configure the selected sensor mode and initialize incident power before enabling.')
    ol.intensity_servo_control.write(0, (ctrl | 1) & ~(1 << 6))
    time.sleep(.001)
    if not status(ol)['active']:
        raise RuntimeError('New intensity path did not become active; inspect status().')
    ol.axi_gpio_9.write(0, 0)  # Release the downstream manual-DAC override.
    return status(ol)


def power_codes(power_mW, *, power_full_scale_mW=POWER_FULL_SCALE_MW):
    """Convert physical power to uint16 setpoints using the selected table scale."""
    power = np.asarray(power_mW, dtype=float)
    if (not math.isfinite(power_full_scale_mW) or power_full_scale_mW <= 0 or
            not np.isfinite(power).all() or np.any(power < 0)):
        raise ValueError('Use finite nonnegative power and positive full scale in mW.')
    code = np.rint(power * 65536 / power_full_scale_mW)
    if np.any(code > 65535):
        raise ValueError('Requested power exceeds the uint16 common power range.')
    return int(code) if code.ndim == 0 else code.astype(np.uint16)


def waveform_words(time_s, power_mW, *, power_full_scale_mW=POWER_FULL_SCALE_MW):
    """Encode sample-and-hold power points for the existing 32-bit dwell streamer.

    power[i] is held on[time[i],time[i+1]); the final value is a time endpoint.
    Long holds split at 65536 FPGA clocks. The final one-clock zero command
    carries TLAST and preserves the existing streamer's end-of-shot convention.
    """
    t = np.asarray(time_s, dtype=float)
    power = np.asarray(power_mW, dtype=float)
    if (t.ndim != 1 or t.shape != power.shape or len(t) < 2 or
            not np.isfinite(t).all() or np.any(np.diff(t) <= 0)):
        raise ValueError('Use paired power/time arrays with strictly increasing times.')
    codes = np.atleast_1d(power_codes(power, power_full_scale_mW=power_full_scale_mW))
    # Quantize edges, not each duration independently. Otherwise a long train
    # of fractional-clock intervals accumulates a waveform-duration error.
    edges = np.rint((t-t[0])*FS_HZ)
    if not np.isfinite(edges).all() or np.any(edges >= 2**63):
        raise ValueError('Waveform times exceed the supported clock-count range.')
    words = []
    for code, clocks in zip(codes[:-1], np.diff(edges.astype(np.int64))):
        clocks = int(clocks)
        if clocks < 1:
            raise ValueError('Each hold must last at least one FPGA clock.')
        while clocks:
            count = min(clocks, 65536)
            words.append((int(code) << 16) | (count-1))
            clocks -= count
    words.append(0)
    return np.asarray(words, dtype=np.uint32)


def manual_power(ol, power_mW, *, power_full_scale_mW=None):
    """Select a manual common-power setpoint for the NEW controller only.

    The legacy PI interprets this GPIO as ADC counts. Use this function only
    after selecting/configuring the new path. Zero is allowed while inactive
    to prepare a safe startup. Existing legacy calibration helpers keep their
    original ADC-count convention.
    """
    check(ol)
    _require_no_shot(ol)
    metadata = getattr(ol, '_intensity_servo_metadata', {})
    scale = power_full_scale_mW if power_full_scale_mW is not None else metadata.get('power_full_scale_mW')
    if scale is None:
        raise ValueError('Supply the same full scale used to construct the sensor LUTs.')
    if power_mW and metadata.get('power_full_scale_mW', scale) != scale:
        raise ValueError('Manual setpoint scale must match the selected sensor table.')
    code = power_codes(power_mW, power_full_scale_mW=scale)
    if code and not status(ol)['active']:
        raise RuntimeError('Enable the calibrated controller at zero before selecting nonzero power.')
    if code:
        mode = 'high_power' if ol.intensity_servo_control.read(0) & 8 else 'low_power'
        if metadata.get('sensor_mode') != mode:
            raise ValueError('Use configure_controller() to switch sensor mode and output scaling together.')
        ranges = metadata.get('sensor_power_limits_mW')
        effective_power = metadata.get('effective_power_mW')
        maximum_fraction = metadata.get('maximum_transmission_fraction')
        if ranges is None or effective_power is None or maximum_fraction is None:
            raise ValueError('Load calibration and initialize incident power before selecting nonzero power.')
        actual_power = code * scale / 65536
        lower, upper = ranges[mode]
        reachable = min(upper, effective_power * maximum_fraction)
        if not lower <= actual_power <= reachable:
            raise ValueError(f'Use zero/off or a {mode} setpoint in [{lower:g}, {reachable:g}] mW; '
                             'the upper bound includes measured sensor and available AOM ranges.')
    ol.axi_gpio_11.write(8, code)
    ol.axi_gpio_11.write(0, 1)
    return code * scale / 65536


def apply_incident_power(ol, effective_power_mW, *, maximum_step_fraction=.05):
    """Bound an estimator update between shots, with an explicit zero reference.

    This briefly disables/resets the new controller and restores its mode. It
    requires manual setpoint zero, no armed DMA, and a known previous scale.
    Use after controller optimization; keep coefficients fixed. Large changes
    should be investigated/reinitialized rather than silently followed.
    """
    _require_no_shot(ol)
    if not 0 < maximum_step_fraction <= .25:
        raise ValueError('Use a positive between-shot step limit no greater than 25%.')
    if not ol.axi_gpio_11.read(0) & 1 or ol.axi_gpio_11.read(8) & 65535:
        raise RuntimeError('Select manual_power(ol,0) between shots before applying an estimate.')
    previous = getattr(ol, '_intensity_servo_metadata', {}).get('effective_power_mW')
    if previous is None or not math.isfinite(effective_power_mW) or effective_power_mW <= 0:
        raise ValueError('Initialize a known positive incident-power scale first.')
    target = float(np.clip(effective_power_mW, previous*(1-maximum_step_fraction), previous*(1+maximum_step_fraction)))
    original_control = int(ol.intensity_servo_control.read(0))
    original_manual_dac = int(ol.axi_gpio_9.read(0))
    safe_off(ol)
    actual = set_incident_power(ol, target)
    ol.intensity_servo_control.write(0, original_control & ~(1 << 6))
    time.sleep(.001)
    ol.axi_gpio_9.write(0, original_manual_dac)
    return dict(effective_power_mW=actual, requested_effective_power_mW=float(effective_power_mW),
                limited=target != effective_power_mW,
                controller_reenabled=bool(original_control & 1))


def load_sensor_table(path, *, adc_bias_counts=0):
    """Read a sensor JSON or a power-meter CSV (setpoint, mean_W).

    CSV setpoints are assumed settled: raw ADC = setpoint - adc_bias_counts.
    Powers are converted to mW. Dark subtraction must be physically measured
    and applied before this function; it does not invent a zero-light point.
    """
    path = Path(path)
    if path.suffix.lower() == '.json':
        result = json.loads(path.read_text())
        if result.get('power_units') == 'W':
            result['optical_power'] = (np.asarray(result['optical_power']) * 1000).tolist()
            result['power_units'] = 'mW'
        if result.get('power_units') != 'mW':
            raise ValueError('Sensor calibration must use W or mW, not relative units.')
    else:
        with path.open(newline='', encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(line for line in stream if not line.startswith('#')))
        result = dict(
            adc_counts=[float(row['setpoint']) - adc_bias_counts for row in rows],
            optical_power=[1000 * float(row['mean_W']) for row in rows],
            power_units='mW', adc_bias_counts=adc_bias_counts,
        )
    result['source_file'] = str(path)
    result['source_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    _sensor_arrays(result)
    return result


def _sensor_arrays(table):
    adc = np.asarray(table['adc_counts'], dtype=float)
    power_mW = np.asarray(table['optical_power'], dtype=float)
    if (adc.ndim != 1 or adc.shape != power_mW.shape or len(adc) < 3 or
            not np.isfinite(adc + power_mW).all() or np.any(np.diff(adc) <= 0) or
            np.any(np.diff(power_mW) <= 0) or power_mW.min() < 0 or
            adc.min() < 0 or adc.max() > 16383 or table.get('power_units') != 'mW'):
        raise ValueError('Provide >=3 increasing ADC counts in 0..16383 and increasing nonnegative power in mW.')
    return adc, power_mW


def make_sensor_luts(low_power_table, high_power_table, *, power_full_scale_mW=POWER_FULL_SCALE_MW,
                     low_power_full_scale_mW=None):
    """Two direct 16384x16 sensor tables, one synchronous read per sample.

    Outside measured ranges, entries clamp to endpoint values; separate ADC
    bounds flag those samples. Clamping is not a validated extrapolation.
    No nonlinear arithmetic is needed in the FPGA sample path. Optionally use
    a smaller low-mode range to reduce rounding there. The upload helper then
    switches setpoint/measurement/output scales together between shots.
    For split ranges, read power_full_scale_by_mode_mW; the old common-scale
    scalar fields are None so they cannot silently apply the wrong mode.
    """
    if not math.isfinite(power_full_scale_mW) or power_full_scale_mW <= 0:
        raise ValueError('Use a positive finite common power full scale in mW.')
    values = np.zeros((2, 16384), dtype=np.uint16)
    scales = dict(low_power=power_full_scale_mW if low_power_full_scale_mW is None else low_power_full_scale_mW,
                  high_power=power_full_scale_mW)
    if not all(np.isfinite(v) and v > 0 for v in scales.values()):
        raise ValueError('Both power full scales must be positive and finite.')
    limits = []
    for bank, table in enumerate((low_power_table, high_power_table)):
        scale = scales[('low_power', 'high_power')[bank]]
        adc, power_mW = _sensor_arrays(table)
        if power_mW.max() >= scale:
            raise ValueError('Each power full scale must exceed that mode\'s calibration maximum.')
        codes = np.rint(np.interp(np.arange(16384), adc, power_mW) * 65536 / scale)
        if np.max(codes) > 65535:
            raise ValueError('Power quantization reaches 65536; increase full scale slightly.')
        values[bank] = codes.astype(np.uint16)
        limits.append([int(np.ceil(adc[0])), int(np.floor(adc[-1]))])
    common = scales['low_power'] == scales['high_power']
    return dict(values=values, adc_limits_counts=limits,
                power_full_scale_mW=float(power_full_scale_mW) if common else None,
                power_per_code_mW=float(power_full_scale_mW / 65536) if common else None,
                power_full_scale_by_mode_mW={key:float(value) for key,value in scales.items()},
                sensor_modes=['low_power', 'high_power'],
                source_sha256=[t.get('source_sha256') for t in (low_power_table, high_power_table)],
                lut_sha256=hashlib.sha256(values.astype('<u2').tobytes()).hexdigest())


def make_output_lut(*, alpha_rad_per_code=AOM_ALPHA_RAD_PER_CODE,
                    maximum_command_codes=AOM_MAXIMUM_MEASURED_CODE,
                    minimum_measured_command_codes=1119.3908788776484):
    """Q0.16 transmission -> RF envelope code, rising sin² branch only.

    Index i represents F=i/65536. F=0 deliberately gives RF off; commands
    between zero and the minimum measured command remain model extrapolation.
    Both hardware transmission limiting and the table cap use the measured
    maximum command. The fitted sin² maximum is not a validated drive limit.
    """
    if (not math.isfinite(alpha_rad_per_code) or alpha_rad_per_code <= 0 or
            not isinstance(maximum_command_codes, (int, np.integer)) or
            not 1 <= maximum_command_codes <= 32767 or
            alpha_rad_per_code * maximum_command_codes >= np.pi / 2 or
            not 0 < minimum_measured_command_codes <= maximum_command_codes):
        raise ValueError('Use a positive alpha and a measured command limit on the rising branch.')
    fraction = np.arange(65536, dtype=float) / 65536
    command = np.rint(np.arcsin(np.sqrt(fraction)) / alpha_rad_per_code)
    command = np.minimum(command, maximum_command_codes).astype(np.uint16)
    maximum_fraction = float(np.sin(alpha_rad_per_code * maximum_command_codes)**2)
    maximum_fraction_code = int(np.floor(maximum_fraction * 65536))
    return dict(values=command, alpha_rad_per_code=float(alpha_rad_per_code),
                maximum_command_codes=int(maximum_command_codes),
                minimum_measured_command_codes=float(minimum_measured_command_codes),
                maximum_fraction_code=maximum_fraction_code,
                maximum_transmission_fraction=maximum_fraction,
                normalization='F=sin(alpha*u)**2; scale includes unmeasured peak efficiency and optical losses',
                lut_sha256=hashlib.sha256(command.astype('<u2').tobytes()).hexdigest())


def aom_table(*, minimum_command_codes=4000, maximum_command_codes=AOM_MAXIMUM_MEASURED_CODE,
              alpha_rad_per_code=AOM_ALPHA_RAD_PER_CODE):
    """Positive fitted transmission samples for the shot-wise scale estimator.

    Default lower bound excludes the measured 3k-code slope anomaly. This
    normalization returns effective power A in P=A*F, not true AOM input power.
    """
    if not 0 < minimum_command_codes < maximum_command_codes <= AOM_MAXIMUM_MEASURED_CODE:
        raise ValueError('Use a positive interval within the measured AOM command range.')
    u = np.arange(minimum_command_codes, maximum_command_codes + 1, dtype=float)
    if alpha_rad_per_code <= 0 or alpha_rad_per_code * u[-1] >= np.pi / 2:
        raise ValueError('AOM model must remain on its rising branch.')
    return dict(u_codes=u, F_relative=np.sin(alpha_rad_per_code * u)**2)


def design_controller(kind='PI', *, kp=None, integral_corners_hz=None,
                      lead_zero_hz=None, lead_pole_hz=None):
    """Quantize C(s)=kp*product(1+2*pi*f_I/s), optional unity-DC lead/lag.

    Integrator increments use forward rectangular integration at 122.88 MHz.
    The optional shelf is(1+s/zero)/(1+s/pole), high-frequency gain pole/zero.
    Positive kp assumes error=reference-measured with increasing power maps.
    Default PI targets approximately300kHz as an experimental starting point;
    PII/PIII target approximately150kHz with wider modelled gain margins.
    The300kHz PI has only~0.17dB predicted gain margin: remeasure before tuning.
    All predictions depend on the supplied large-modulation plant measurement.
    """
    names = {'PI': 1, 'PII': 2, 'PIII': 3}
    if kind not in names:
        raise ValueError('Select PI, PII or PIII.')
    order = names[kind]
    if kp is None:
        kp = 1.00840 if kind == 'PI' else 0.35280
    if integral_corners_hz is None:
        integral_corners_hz = ([50e3] if kind == 'PI' else [400e3, 1e3, 100][:order])
    corners = np.asarray(integral_corners_hz, dtype=float)
    if corners.shape != (order,) or not np.isfinite(corners).all() or np.any(corners < 0):
        raise ValueError(f'Provide{order} finite nonnegative integral corners in Hz.')
    alpha = np.rint(2 * np.pi * corners / INTEGRATOR_FS_HZ * 2**24).astype(np.int64)
    kp_code = round(float(kp) * 4096)
    if not math.isfinite(kp) or not -(2**17) <= kp_code < 2**17 or np.any(alpha >= 2**20):
        raise ValueError('Gain must fit signed Q6.12 and integrator coefficients unsigned 20-bit Q24.')
    enabled = lead_zero_hz is not None or lead_pole_hz is not None
    if enabled:
        if (lead_zero_hz is None or lead_pole_hz is None or
                not np.isfinite([lead_zero_hz, lead_pole_hz]).all() or
                min(lead_zero_hz, lead_pole_hz) <= 0):
            raise ValueError('Supply both positive finite lead zero and pole frequencies.')
        shelf_gain = round(lead_pole_hz / lead_zero_hz * 4096)
        shelf_alpha = round(-np.expm1(-2 * np.pi * lead_pole_hz / INTEGRATOR_FS_HZ) * 2**30)
        if not 0 < shelf_gain < 2**17 or not 0 < shelf_alpha <= 2**30:
            raise ValueError('Lead/lag coefficients exceed the hardware range.')
    else:
        shelf_gain, shelf_alpha = 4096, 0
    return dict(kind=kind, order=order, kp_q12=int(kp_code),
                alpha_q24=(alpha.tolist() + [0, 0, 0])[:3],
                kp_actual=kp_code / 4096,
                integral_corners_actual_hz=(alpha / 2**24 * INTEGRATOR_FS_HZ / (2*np.pi)).tolist(),
                leadlag_enable=bool(enabled), leadlag_gain_q12=int(shelf_gain),
                leadlag_alpha_q30=int(shelf_alpha),
                lead_zero_hz=lead_zero_hz, lead_pole_hz=lead_pole_hz,
                integrator_update_rate_hz=INTEGRATOR_FS_HZ)


def controller_response(frequency_hz, coefficients, *, additional_delay_s=0.):
    """Small-signal frequency model; pipeline delay must be supplied explicitly.

    Uses the quantized half-rate integrator/shelf recurrence. The implemented
    proportional path runs at full rate, so this scalar model neglects tiny
    sample-periodic effects and must be checked against new FRA measurements.
    """
    f = np.asarray(frequency_hz, dtype=float)
    if np.any(f <= 0) or np.any(f >= INTEGRATOR_FS_HZ / 2) or additional_delay_s < 0:
        raise ValueError('Use 0 < f < 61.44 MHz and a nonnegative added delay.')
    zinv = np.exp(-2j*np.pi*f/INTEGRATOR_FS_HZ)
    response = np.full(f.shape, coefficients['kp_q12']/4096, dtype=complex)
    for alpha in coefficients['alpha_q24'][:coefficients['order']]:
        response *= 1 + alpha/2**24 * zinv/(1-zinv)
    if coefficients['leadlag_enable']:
        alpha = coefficients['leadlag_alpha_q30']/2**30
        gain_inf = coefficients['leadlag_gain_q12']/4096
        state = alpha*zinv/(1-(1-alpha)*zinv)
        response *= 1+(gain_inf-1)*(1-state)
    return response*np.exp(-2j*np.pi*f*additional_delay_s)


def predict_loop(fra_csv, coefficients, *, dc_fractional_gain_per_code=3.2962287322463063e-4,
                 additional_delay_s=None):
    """Predict a normalized-power loop from measured K=Q/(P0*U), not old L.

    additional_delay_s is only the new controller/map delay beyond the two FRA
    tap locations. Default is eleven clocks (44.76ns), plus two clocks if the
    shelf is enabled. The supplied FRA already contains the INT2 receive filter.
    Prediction applies only over measured frequencies and around the measured
    operating point. Large-dither measurements require a small-signal recheck.
    """
    rows = np.genfromtxt(fra_csv, delimiter=',', names=True, dtype=None, encoding='utf-8')
    f = np.asarray(rows['frequency_hz'], dtype=float)
    if additional_delay_s is None:
        additional_delay_s = FAST_FEEDBACK_DELAY_S + (2/FS_HZ if coefficients['leadlag_enable'] else 0)
    plant = (rows['K_re']+1j*rows['K_im'])/dc_fractional_gain_per_code
    if dc_fractional_gain_per_code <= 0 or np.any(np.diff(f) <= 0):
        raise ValueError('Use positive DC gain and frequency-sorted measured data.')
    loop = plant*controller_response(f, coefficients, additional_delay_s=additional_delay_s)
    return dict(frequency_hz=f, normalized_plant=plant, loop=loop,
                sensitivity=1/(1+loop), complementary=loop/(1+loop),
                additional_delay_s=float(additional_delay_s))
