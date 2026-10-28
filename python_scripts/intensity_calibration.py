"""Intensity-branch sample-resolved FRA and drift-normalized AOM calibration.

ADC224/1 -> unchanged PI -> DAC228/3. No calibration table is applied to feedback.
The image-filtered I sample is replicated in four lanes for format compatibility.
Sensor calibration is applied after RF image removal and before fitting. The saved
record contains actual total command u, selected controller command c, and DDS
phase; d=u-c, return ratio L=-C/U, and K=Q/(P0*U) has units 1/DAC-code.
"""

import csv
import json
import math
import time
from pathlib import Path

import numpy as np

FS_HZ = 245.76e6
FEATURE_VERSION = 0x494E5402
FAULT_NAMES = {
    2: 'capture overflow',
    3: 'ADC invalid/DAC stall',
    4: 'actuator clipping',
    5: 'PI at rail',
    6: 'ADC at rail',
    9: 'diagnostic configuration changed',
}


def check(ol):
    for name in (
        'intensity_control',
        'intensity_tone',
        'intensity_limits',
        'intensity_counts',
        'intensity_dma',
    ):
        if name not in ol.ip_dict:
            raise ValueError(f'Missing {name}; load the matched intensity bit/HWH.')
    if ol.intensity_limits.read(8) != FEATURE_VERSION:
        raise ValueError('Intensity feature signature mismatch; check bit/HWH pairing.')


def configuration(ol):
    """Read operating-point settings without altering any feedback controls."""
    pi = ol.fast_servo_controller_0
    rf = ol.usp_rf_data_converter_0
    return dict(
        pi_registers={hex(a): pi.read(a) for a in (0x10, 0x18, 0x20, 0x28, 0x30)},
        gpio={str(n): [getattr(ol, f'axi_gpio_{n}').read(a) for a in (0, 8)] for n in (9, 10, 11, 12)},
        adc_mixer=dict(rf.adc_tiles[0].blocks[1].MixerSettings),
        lo_mixer=dict(rf.dac_tiles[0].blocks[1].MixerSettings),
        aom_mixer=dict(rf.dac_tiles[0].blocks[3].MixerSettings),
        limits_word=ol.intensity_limits.read(0) if 'intensity_limits' in ol.ip_dict else 0x7FFF0000,
    )


def restore_manual_configuration(ol, saved):
    """Cold-start restore of known working settings, NOT a bumpless live update.

    Save configuration() before reprogramming. Serial streamer memory and PI
    integrator state cannot be restored; require a saved manual setpoint.
    """
    check(ol)
    if not saved['gpio']['11'][0] & 1 or not saved['gpio']['11'][1] & 65535:
        raise ValueError('Save a nonzero manual setpoint before reprogramming.')
    import xrfdc

    pi = ol.fast_servo_controller_0
    stop(ol)
    pi.write(0x10, 0)
    ol.axi_gpio_9.write(8, 0)
    ol.axi_gpio_9.write(0, 1)
    rf = ol.usp_rf_data_converter_0
    for block, name in [
        (rf.adc_tiles[0].blocks[1], 'adc_mixer'),
        (rf.dac_tiles[0].blocks[1], 'lo_mixer'),
        (rf.dac_tiles[0].blocks[3], 'aom_mixer'),
    ]:
        block.MixerSettings = dict(saved[name])
        block.UpdateEvent(xrfdc.EVENT_MIXER)
    for n in (10, 11, 12):
        for a, v in zip((0, 8), saved['gpio'][str(n)]):
            getattr(ol, f'axi_gpio_{n}').write(a, v)
    for a in (0x18, 0x20, 0x28, 0x30):
        pi.write(a, saved['pi_registers'][hex(a)])
    ol.intensity_limits.write(0, saved.get('limits_word', 0x7FFF0000))
    ol.axi_gpio_9.write(8, saved['gpio']['9'][1])
    pi.write(0x10, saved['pi_registers']['0x10'])
    ol.axi_gpio_9.write(0, saved['gpio']['9'][0])


def manual_setpoint(ol, counts):
    """Select signed ADC-count setpoint; zero disables/resets the existing PI."""
    if not isinstance(counts, int) or not -32768 <= counts <= 32767:
        raise ValueError('Setpoint must be an integer signed 16-bit ADC count.')
    ol.axi_gpio_11.write(8, counts & 65535)
    ol.axi_gpio_11.write(0, 1)


def stop(ol):
    """Ramp off only intensity dither; preserve the PI, setpoint and RF mixers."""
    check(ol)
    ol.intensity_control.write(0, ol.intensity_control.read(0) & ~1)
    deadline = time.monotonic() + 0.2
    while ol.intensity_control.read(8) & (1 << 8):
        if time.monotonic() > deadline:
            raise TimeoutError('Intensity tone did not ramp off.')
        time.sleep(0.001)


def plan(frequency_hz, *, cycles=16, minimum_measure_s=0.02, decimation_log2=None):
    if not math.isfinite(frequency_hz) or not 10 <= frequency_hz <= 1e6:
        raise ValueError('Use 10 Hz to 1 MHz.')
    if (
        not math.isfinite(cycles)
        or cycles < 4
        or not math.isfinite(minimum_measure_s)
        or minimum_measure_s <= 0
    ):
        raise ValueError('Use at least four cycles and positive block duration.')
    word = round(frequency_hz / FS_HZ * 2**32)
    actual_hz = word * FS_HZ / 2**32
    if decimation_log2 is None:
        decimation_log2 = max(3, min(20, math.floor(math.log2(FS_HZ / max(250e3, 16 * actual_hz)))))
    if not isinstance(decimation_log2, int) or not 3 <= decimation_log2 <= 20:
        raise ValueError('Capture D must be an integer from 3 to 20.')
    sample_rate_hz = FS_HZ / 2**decimation_log2
    if sample_rate_hz < 16 * actual_hz:
        raise ValueError('Capture at least 16 samples per dither period.')
    n_cycles = math.ceil(max(cycles, actual_hz * minimum_measure_s))
    samples = round(n_cycles / actual_hz * sample_rate_hz)
    if not 64 <= samples <= 1048575:
        raise ValueError('Block exceeds capture size; shorten it or increase D within the sampling limit.')
    return dict(
        frequency_hz=actual_hz,
        frequency_word=word,
        decimation_log2=decimation_log2,
        samples=samples,
        sample_rate_hz=sample_rate_hz,
        duration_s=samples / sample_rate_hz,
    )


def capture(ol, *, samples=32768, decimation_log2=8):
    """Filtered finite capture; four identical I lanes, in original ADC-count units."""
    check(ol)
    if not isinstance(samples, int) or not 1 <= samples <= 1048575:
        raise ValueError('samples must be in [1,1048575].')
    if not isinstance(decimation_log2, int) or not 3 <= decimation_log2 <= 20:
        raise ValueError('decimation_log2 must be in [3,20].')
    ctrl = ol.intensity_control
    if ctrl.read(0) & 2:
        raise RuntimeError('An intensity capture is already armed.')
    from pynq import allocate

    dma = ol.intensity_dma
    buffer = allocate(shape=(samples, 4), dtype=np.uint32)
    started = False
    try:
        if not dma.recvchannel.running:
            dma.recvchannel.start()
        dma.recvchannel.transfer(buffer)
        started = True
        ctrl.write(0, (ctrl.read(0) & 1) | 2 | (decimation_log2 << 3) | (samples << 12))
        deadline = time.monotonic() + samples * 2**decimation_log2 / FS_HZ + 3.0
        while not dma.recvchannel.idle:
            if dma.mmio.read(0x34) & 0x70:
                raise RuntimeError('Intensity DMA transfer error.')
            if time.monotonic() > deadline:
                raise TimeoutError('Intensity capture timed out.')
            time.sleep(0.001)
        dma.recvchannel.wait()
        started = False
        word = ctrl.read(8)
        if not word & 2 or word >> 12 != samples:
            raise RuntimeError('Incomplete intensity capture.')
        return dict(
            raw=np.array(buffer),
            feature_version=FEATURE_VERSION,
            receiver_filter="15-tap FIR after four-lane mean; replicated I",
            receiver_added_delay_s=11/FS_HZ,
            sample_rate_hz=FS_HZ / 2**decimation_log2,
            decimation_log2=decimation_log2,
            status=word,
            clip_samples=ol.intensity_counts.read(0),
            invalid_samples=ol.intensity_counts.read(8),
        )
    finally:
        ctrl.write(0, ctrl.read(0) & 1)
        if started:
            dma.recvchannel.stop()
            dma.recvchannel.start()
        buffer.freebuffer()


def unpack(record):
    raw = np.asarray(record['raw'], dtype=np.uint32)
    i_counts = raw[:, :2].copy().view(np.int16).reshape(-1, 4)
    commands = raw[:, 2].copy().view(np.int16).reshape(-1, 2)
    return (
        i_counts,
        commands[:, 0].astype(float),
        commands[:, 1].astype(float),
        raw[:, 3].astype(float) * 2 * np.pi / 2**32,
    )


def sensor_table(adc_counts, optical_power, *, power_units='relative'):
    """Monotonic, offset-corrected sensor calibration. Include measured dark point.

    optical_power must already have unwanted additive optical background removed;
    zero optical input is assigned zero power, at its measured ADC count.
    """
    x = np.asarray(adc_counts, dtype=float)
    y = np.asarray(optical_power, dtype=float)
    if x.ndim != 1 or x.shape != y.shape or len(x) < 3 or not np.all(np.isfinite(x + y)):
        raise ValueError('Provide >=3 finite, paired calibration points.')
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    if not np.all(np.diff(x) > 0) or not (np.all(np.diff(y) > 0) or np.all(np.diff(y) < 0)):
        raise ValueError('Use one strictly monotonic sensor branch; revisit inconsistent points.')
    return dict(adc_counts=x.tolist(), optical_power=y.tolist(), power_units=power_units)


def linearize(i_counts, table):
    """Apply calibration to EVERY raw lane before taking any sample means."""
    x = np.asarray(table['adc_counts'])
    y = np.asarray(table['optical_power'])
    if np.min(i_counts) < x[0] or np.max(i_counts) > x[-1]:
        raise ValueError('Sensor samples leave the calibrated range; extend calibration, do not extrapolate.')
    return np.interp(i_counts, x, y).mean(axis=1)


def analyze(record, table=None):
    """Fit x0 + x1*(t-tc) + xc*cos(theta) + xs*sin(theta), phasor xc-i*xs.

    Within-block fit errors assume white residuals; repeated-block scatter is
    used by sweep() for reported transfer uncertainty. K requires a sensor table.
    """
    i, c, u, theta = unpack(record)
    raw_sensor = i.mean(axis=1)
    flags = [name for bit, name in FAULT_NAMES.items() if record['status'] & (1 << bit)]
    optical_response_missing = False
    try:
        p = raw_sensor if table is None else linearize(i, table)
    except ValueError:
        if not flags:
            raise
        # A flagged ADC glitch/rail may leave the table. Keep this rejected
        # block and its command data, without extrapolating an optical response.
        p = np.zeros(len(u))  # Keep NaNs out of the least-squares solver.
        optical_response_missing = True
    t = (np.arange(len(u)) - (len(u) - 1) / 2) / record['sample_rate_hz']
    design = np.column_stack((np.ones(len(u)), t, np.cos(theta), np.sin(theta)))
    signals = np.column_stack((c, u, p))
    coeff, _, rank, _ = np.linalg.lstsq(design, signals, rcond=None)
    if rank != 4:
        raise ValueError('Record does not resolve offset, drift and quadratures.')
    if optical_response_missing:
        coeff[:, 2] = np.nan
        signals[:, 2] = np.nan
    c0, u0, p0 = coeff[0]
    C, U, Q = coeff[2] - 1j * coeff[3]
    D = U - C
    residual = signals - design @ coeff
    cov = np.linalg.inv(design.T @ design)
    sem = np.sqrt((cov[2, 2] + cov[3, 3]) * np.sum(residual**2, axis=0) / (len(u) - 4))
    duration_s = len(u) / record['sample_rate_hz']
    return dict(
        u0_codes=float(u0),
        p0=float(p0),
        raw_sensor_mean=float(raw_sensor.mean()),
        C=complex(C),
        U=complex(U),
        Q=complex(Q),
        D=complex(D),
        loop=-C / U if abs(U) > 0 else complex(np.nan, np.nan),
        K=Q / (p0 * U) if table is not None and p0 > 0 and abs(U) > 0 else complex(np.nan, np.nan),
        power_units=table.get('power_units', 'calibrated') if table is not None else 'ADC counts',
        fractional_modulation=abs(Q / p0) if table is not None and p0 > 0 else float('nan'),
        power_drift_fraction=abs(float(coeff[1, 2]) * duration_s / p0) if p0 != 0 else float('inf'),
        command_drift_codes=float(coeff[1, 1]) * duration_s,
        fit_u_sem_codes=float(sem[1]),
        fit_q_sem=float(sem[2]),
        flags=flags,
        duration_s=duration_s,
    )


def measure_point(
    ol,
    frequency_hz,
    *,
    amplitude_codes=32,
    table=None,
    minimum_measure_s=0.02,
    settle_s=0.05,
    cycles=16,
    decimation_log2=None,
    polarity=1,
    raw_path=None,
):
    """One block, closed feedback active. Never changes the PI, setpoint or RFDC."""
    check(ol)
    if not isinstance(amplitude_codes, int) or not 1 <= amplitude_codes <= 32767 or polarity not in (-1, 1):
        raise ValueError('Use integer amplitude 1..32767, polarity +/-1.')
    if not math.isfinite(settle_s) or settle_s < 0:
        raise ValueError('settle_s must be nonnegative.')
    if ol.intensity_control.read(0) & 3:
        raise RuntimeError('Intensity diagnostic is already active; call stop first.')
    before = configuration(ol)
    limits = before['limits_word']
    if not 0 <= limits & 65535 < limits >> 16 <= 32767:
        raise ValueError('Dither limits must satisfy 0 <= minimum < maximum <= 32767.')
    if not before['pi_registers']['0x10'] or before['gpio']['9'][0] & 1:
        raise ValueError('Enable the existing intensity PI and select its closed-loop output first.')
    if not before['gpio']['11'][0] & 1 or not before['gpio']['11'][1] & 65535:
        raise ValueError('Select a nonzero manual optical setpoint before running this measurement.')
    window = plan(
        frequency_hz, cycles=cycles, minimum_measure_s=minimum_measure_s, decimation_log2=decimation_log2
    )
    try:
        ol.intensity_tone.write(0, window['frequency_word'])
        ol.intensity_tone.write(8, (polarity * amplitude_codes) & 65535)
        ol.intensity_control.write(0, 1)
        time.sleep(max(settle_s, 5 / window['frequency_hz']) + 0.002)
        record = capture(ol, samples=window['samples'], decimation_log2=window['decimation_log2'])
        metadata = dict(
            configuration=before,
            window=window,
            amplitude_codes=amplitude_codes,
            polarity=polarity,
            sensor_table=table,
        )
        if raw_path is not None:
            np.savez_compressed(raw_path, **record, metadata_json=json.dumps(metadata))
        if configuration(ol) != before:
            raise RuntimeError('Intensity operating settings changed during measurement.')
        result = analyze(record, table)
        for key in ('C', 'U', 'Q', 'D'):
            result[key] *= polarity
        return {
            **window,
            **result,
            'amplitude_codes': amplitude_codes,
            'polarity': polarity,
            'status': record['status'],
            'clip_samples': record['clip_samples'],
            'invalid_samples': record['invalid_samples'],
        }
    finally:
        stop(ol)


def _csv(path, rows):
    if not rows:
        return
    flat = []
    for row in rows:
        out = {}
        for k, v in row.items():
            if isinstance(v, complex):
                out[k + '_re'] = v.real
                out[k + '_im'] = v.imag
            elif isinstance(v, list):
                out[k] = '; '.join(v)
            else:
                out[k] = v
        flat.append(out)
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)


def sweep(
    ol,
    frequencies_hz,
    *,
    amplitude_codes=32,
    table=None,
    repeats=8,
    max_repeats=24,
    target_snr=10.0,
    maximum_drift_fraction=0.03,
    maximum_command_drift_fraction=0.02,
    csv_path='intensity_fra.csv',
    **window,
):
    """Repeat short blocks; save raw NPZs, all block fits, and complex-mean FRA.

    Diagnostic clipping/invalid blocks are retained on disk and excluded. DMA,
    settings, and calibration failures stop. Amplitude may be a scalar or a list
    matching frequencies. No automatic gain adjustment or relocking is done.
    """
    frequencies = np.atleast_1d(frequencies_hz).astype(float)
    if frequencies.ndim != 1 or not len(frequencies):
        raise ValueError('Provide a nonempty frequency list.')
    amplitudes = np.broadcast_to(amplitude_codes, frequencies.shape)
    if (
        not np.all(np.isfinite(amplitudes))
        or np.any(amplitudes != np.round(amplitudes))
        or np.any((amplitudes < 1) | (amplitudes > 32767))
    ):
        raise ValueError('Amplitudes must be integer codes from 1 to 32767.')
    if not isinstance(repeats, int) or not isinstance(max_repeats, int) or not 2 <= repeats <= max_repeats:
        raise ValueError('Use integer 2 <= repeats <= max_repeats.')
    if not all(
        math.isfinite(v) and v > 0
        for v in (target_snr, maximum_drift_fraction, maximum_command_drift_fraction)
    ):
        raise ValueError('Quality thresholds must be finite and positive.')
    for frequency_hz in frequencies:
        plan(frequency_hz, **{k: v for k, v in window.items() if k != 'settle_s'})
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_dir = path.with_suffix('')
    raw_dir.mkdir(exist_ok=False)
    config = configuration(ol)
    path.with_suffix('.json').write_text(
        json.dumps(
            dict(
                configuration=config,
                sensor_table=table,
                frequencies_hz=frequencies.tolist(),
                amplitude_codes=amplitudes.tolist(),
                repeats=repeats,
                max_repeats=max_repeats,
                target_snr=target_snr,
                maximum_drift_fraction=maximum_drift_fraction,
                maximum_command_drift_fraction=maximum_command_drift_fraction,
                window=window,
            ),
            indent=2,
        )
    )
    rows = []
    blocks = []
    for index, (f, a) in enumerate(zip(frequencies, amplitudes)):
        accepted = []
        snr_u = snr_q = snr_c = 0.0
        u_sem = q_sem = c_sem = float('nan')
        for attempt in range(max_repeats):
            if configuration(ol) != config:
                raise RuntimeError('Operating settings changed during sweep.')
            raw_path = raw_dir / f'point_{index:03d}_block_{attempt:03d}.npz'
            p = measure_point(
                ol,
                float(f),
                amplitude_codes=int(a),
                table=table,
                polarity=1 if attempt % 2 == 0 else -1,
                raw_path=raw_path,
                **window,
            )
            rejected = []
            if p['flags']:
                rejected.append('hardware fault')
            if p['power_drift_fraction'] > maximum_drift_fraction:
                rejected.append('power drift')
            # With feedback active, upstream drift can move u while P stays flat.
            if abs(p['command_drift_codes']) > maximum_command_drift_fraction * max(abs(p['u0_codes']), 1):
                rejected.append('command drift')
            if table is not None and p['p0'] <= 0:
                rejected.append('nonpositive power')
            keep = not rejected
            blocks.append(
                dict(**p, accepted=keep, rejection_reason='; '.join(rejected), raw_file=str(raw_path))
            )
            _csv(path.with_name(path.stem + '_blocks.csv'), blocks)
            if keep:
                accepted.append(p)
            if len(accepted) < 2:
                continue
            u = np.array([b['U'] for b in accepted])
            q = np.array([b['Q'] for b in accepted])
            c = np.array([b['C'] for b in accepted])
            u_sem = float(np.std(u, ddof=1) / np.sqrt(len(u)))
            q_sem = float(np.std(q, ddof=1) / np.sqrt(len(q)))
            c_sem = float(np.std(c, ddof=1) / np.sqrt(len(c)))
            snr_u = abs(u.mean()) / max(u_sem, 1e-30)
            snr_q = abs(q.mean()) / max(q_sem, 1e-30)
            snr_c = abs(c.mean()) / max(c_sem, 1e-30)
            if len(accepted) >= repeats and min(snr_u, snr_q, snr_c) >= target_snr:
                break
        nan = complex(np.nan, np.nan)
        C, U, Q, D = [
            complex(np.mean([b[k] for b in accepted])) if accepted else nan for k in ('C', 'U', 'Q', 'D')
        ]
        loop = -C / U if abs(U) > 0 else nan
        # Normalize optical response per block BEFORE averaging, but divide by
        # mean U only once; averaging ratios with a noisy denominator is biased.
        fractional = np.array([b['Q'] / b['p0'] for b in accepted]) if table is not None else np.array([])
        K = complex(fractional.mean() / U) if len(fractional) and abs(U) > 0 else nan
        residual = fractional - K * np.array([b['U'] for b in accepted]) if len(fractional) else np.array([])
        k_sem = (
            float(np.std(residual, ddof=1) / np.sqrt(len(residual)) / abs(U))
            if len(residual) > 1 and abs(U) > 0
            else float('nan')
        )
        loop_res = np.array([b['C'] + loop * b['U'] for b in accepted])
        loop_sem = (
            float(np.std(loop_res, ddof=1) / np.sqrt(len(loop_res)) / abs(U))
            if len(loop_res) > 1 and abs(U) > 0
            else float('nan')
        )
        row = dict(
            frequency_hz=p['frequency_hz'],
            amplitude_codes=int(a),
            accepted_blocks=len(accepted),
            attempts=attempt + 1,
            reliable=bool(len(accepted) >= repeats and min(snr_u, snr_q, snr_c) >= target_snr),
            loop_reliable=bool(len(accepted) >= repeats and min(snr_u, snr_c) >= target_snr),
            plant_reliable=bool(len(accepted) >= repeats and min(snr_u, snr_q) >= target_snr),
            C=C,
            U=U,
            Q=Q,
            D=D,
            loop=loop,
            loop_complex_sem=loop_sem,
            K=K,
            K_complex_sem=k_sem,
            u0_codes=float(np.mean([b['u0_codes'] for b in accepted])) if accepted else float('nan'),
            p0=float(np.mean([b['p0'] for b in accepted])) if accepted else float('nan'),
            u_sem_codes=u_sem,
            q_sem=q_sem,
            c_sem_codes=c_sem,
            u_snr=snr_u,
            q_snr=snr_q,
            c_snr=snr_c,
            power_units=table.get('power_units', 'calibrated') if table is not None else 'ADC counts',
        )
        rows.append(row)
        _csv(path, rows)
        print(
            f"{row['frequency_hz']:.3f} Hz: accepted {len(accepted)}/{attempt+1}, U SNR {snr_u:.1f}, reliable={row['reliable']}"
        )
    return rows


def reconstruct(u_codes, k_per_code, *, maximum_gap_codes):
    """Integrate signed, quasi-static k=d(log F)/du on ONE monotonic branch.

    Feed reviewed/binned real slopes only; never abs(K). No extrapolation or
    hidden smoothing. Relative F is normalized to one at the largest value.
    """
    u = np.asarray(u_codes, dtype=float)
    k = np.asarray(k_per_code, dtype=float)
    if not math.isfinite(maximum_gap_codes) or maximum_gap_codes <= 0:
        raise ValueError('Use a finite positive maximum gap.')
    if u.ndim != 1 or u.shape != k.shape or len(u) < 3 or not np.all(np.isfinite(u + k)):
        raise ValueError('Provide >=3 finite command/slope pairs.')
    order = np.argsort(u)
    u = u[order]
    k = k[order]
    du = np.diff(u)
    if np.any(du <= 0) or np.any(du > maximum_gap_codes):
        raise ValueError('Bin repeated commands and fill large calibration gaps first.')
    if not (np.all(k > 0) or np.all(k < 0)):
        raise ValueError('Select one monotonic branch, away from zero-slope points.')
    ell = np.r_[0, np.cumsum(0.5 * (k[1:] + k[:-1]) * du)]
    F = np.exp(ell - ell.max())
    order = np.argsort(F)
    return dict(u_codes=u, F_relative=F, inverse_transmission=F[order], inverse_u_codes=u[order])


def bin_slopes(blocks, *, bin_width_codes=256, maximum_phase_deg=10, minimum_blocks=3):
    """Bin already-reviewed quasi-static blocks by ACTUAL mean command.

    Phase must be near 0 or 180 degrees; the sign is retained. This check alone
    cannot establish a static plateau: compare nearby frequencies first.
    Returned scatter includes drift/nonrepeatability, not just fit residuals.
    """
    if bin_width_codes <= 0 or not 0 < maximum_phase_deg < 90 or minimum_blocks < 2:
        raise ValueError('Use positive bins, 0<phase tolerance<90 deg, and >=2 blocks.')
    bins = {}
    for row in blocks:
        if not row['accepted']:
            continue
        k = complex(row['K_re'], row['K_im']) if 'K_re' in row else row['K']
        if (
            not np.isfinite(k)
            or k.real == 0
            or abs(k.imag) > abs(k.real) * np.tan(np.deg2rad(maximum_phase_deg))
        ):
            continue
        if abs(row.get('U', complex(row.get('U_re', 0), row.get('U_im', 0)))) < 5 * row['fit_u_sem_codes']:
            continue
        if abs(row.get('Q', complex(row.get('Q_re', 0), row.get('Q_im', 0)))) < 5 * row['fit_q_sem']:
            continue
        index = math.floor(row['u0_codes'] / bin_width_codes)
        bins.setdefault(index, []).append((row['u0_codes'], k.real))
    result = []
    for index, values in sorted(bins.items()):
        if len(values) < minimum_blocks:
            continue
        a = np.array(values)
        result.append(
            dict(
                u_codes=float(a[:, 0].mean()),
                k_per_code=float(a[:, 1].mean()),
                k_std=float(a[:, 1].std(ddof=1)),
                k_sem=float(a[:, 1].std(ddof=1) / np.sqrt(len(a))),
                blocks=len(a),
                command_span_codes=float(np.ptp(a[:, 0])),
            )
        )
    return result


def inverse_command(table, relative_transmission):
    """Piecewise-linear monotonic inverse, limited to the measured branch."""
    v = np.asarray(relative_transmission, dtype=float)
    lo, hi = table['inverse_transmission'][0], table['inverse_transmission'][-1]
    if np.any(~np.isfinite(v)) or np.any(v < lo) or np.any(v > hi):
        raise ValueError('Requested transmission outside calibration.')
    return np.interp(v, table['inverse_transmission'], table['inverse_u_codes'])
