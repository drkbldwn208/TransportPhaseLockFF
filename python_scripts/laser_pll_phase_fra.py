"""R7 FRA extension: received phase versus error injection or RF phase injection.

Closed mode: D is injected after the error/IIR; measure received phase Phi and
total DAC command U. Phi/D is the closed-loop phase response, L=(D-U)/U.
RF mode: phase-modulate DAC229/2; measure Phi_rx/Phi_tx through ADC224/3.
All phasors are peak amplitudes with delay giving negative phase. The two modes
share the primary PLL's existing generator/demodulators and cannot run together.
"""
import csv
import math
import time
from pathlib import Path

import numpy as np
import laser_pll
import laser_pll_loop_sweep as fra

FEATURE_VERSION = 0x52463701
PHASE_CODES_PER_RAD = (1 << 18)/(2*math.pi)


def check_helpers(ol):
    if (getattr(laser_pll, 'FPGA_VERSION', None) != 0xA7 or fra.laser_pll is not laser_pll
            or not callable(getattr(fra, 'diagnostics', None))):
        raise ValueError('Reload the matching R7 control, loop-sweep and phase-FRA helpers together.')
    if ol.pll_acquisition_status.read(8) >> 24 != 0xA7:
        raise ValueError('Load the R7 FRA bitstream/HWH, not the A8 DAC-loopback image.')
    if not hasattr(ol, 'pll_rf_source') or ol.pll_rf_source.read(8) != FEATURE_VERSION:
        raise ValueError('This requires the R7 RF-FRA extension, not the original R7 bitstream/HWH.')


def stop(ol):
    """Ramp off the probe only. Retain the optical feedback state and RF carrier."""
    fra.stop(ol)


def rf_settings(ol):
    rf = ol.usp_rf_data_converter_0
    return dict(adc_mixer=dict(rf.adc_tiles[0].blocks[3].MixerSettings),
                rf_dac_mixer=dict(rf.dac_tiles[1].blocks[2].MixerSettings),
                error_dac_mixer=dict(rf.dac_tiles[1].blocks[1].MixerSettings),
                rf_amplitude_codes=ol.pll_rf_source.read(0) & 65535)


def setup_rf(ol, *, carrier_hz=800.01e6, carrier_amplitude_codes=8192):
    """Open-loop test: DAC229/2 -> RF chain -> ADC224/3, controllers disconnected.

    Mutates ONLY primary PLL and DAC229/2 setup. Error DAC229/1 is held at code
    zero while its receiver remains running. This explicitly replaces the live
    primary lock: reacquire it with normal R7 controls after the RF-chain test.
    Carrier frequency is controlled by the same RFDC mixer used previously.
    """
    check_helpers(ol)
    if not math.isfinite(carrier_hz) or not 200e6 <= carrier_hz <= 900e6:
        raise ValueError('Use a first-zone carrier in 200..900 MHz, normally 800.01 MHz.')
    if not isinstance(carrier_amplitude_codes, int) or not 1 <= carrier_amplitude_codes <= 32767:
        raise ValueError('Carrier amplitude must be 1..32767 DAC codes; verify physical RF power.')
    params = ol.ip_dict['usp_rf_data_converter_0']['parameters']
    if int(params['DAC_Interpolation_Mode12']) != 4 or int(params['DAC_Data_Width12']) != 14:
        raise ValueError('DAC229/2 must retain the R7 interpolation and seven-I/Q-pair format.')
    import xrfdc
    stop(ol)
    laser_pll.enable(ol, False)
    ol.pll_rf_source.write(0, 0)
    dac = ol.usp_rf_data_converter_0.dac_tiles[1].blocks[2]
    cfg = dict(dac.MixerSettings)
    cfg.update(Freq=carrier_hz/1e6, PhaseOffset=0.0, EventSource=xrfdc.EVNT_SRC_IMMEDIATE,
               MixerType=xrfdc.MIXER_TYPE_FINE, MixerMode=xrfdc.MIXER_MODE_C2R,
               FineMixerScale=xrfdc.MIXER_SCALE_1P0)
    dac.MixerSettings = cfg
    dac.ResetNCOPhase()
    dac.UpdateEvent(xrfdc.EVENT_MIXER)
    actual_carrier_hz = dac.MixerSettings['Freq']*1e6
    laser_pll.configure(ol, reference_frequency_hz=actual_carrier_hz, minimum_amplitude=16)
    laser_pll.enable_iir(ol, False)
    laser_pll.set_dc_output(ol, 0)
    ol.pll_rf_source.write(0, carrier_amplitude_codes)
    laser_pll.enable(ol)
    deadline = time.monotonic()+2
    while True:
        state = laser_pll.acquisition_status(ol)
        if state['stage'] == 5 and state['output_valid'] and not state['transitioning']:
            break
        if time.monotonic() > deadline:
            raise TimeoutError('Open-loop DC-zero handoff did not settle.')
        time.sleep(.002)
    return dict(carrier_hz=actual_carrier_hz, carrier_amplitude_codes=carrier_amplitude_codes,
                settings=rf_settings(ol))


def _ready(ol, mode):
    check_helpers(ol)
    if mode == 'closed':
        fra._ready(ol)
    elif mode == 'rf':
        state = laser_pll.acquisition_status(ol)
        if (state['stage'] != 5 or state['transitioning'] or not state['output_valid']
                or not ol.pll_control.read(0) & 1 or ol.pll_acquisition.read(8) & 65535
                or ol.pll_iir.read(0) & 1):
            raise ValueError('Call setup_rf() first: enabled receiver, DC code zero, IIR bypass.')
        if ol.pll_fra.read(0) & 1 or ol.pll_fra.read(8) & 1:
            raise ValueError('Stop the previous analyzer run first.')
        word = ((ol.pll_frequency.read(8) & 65535) << 32) | ol.pll_frequency.read(0)
        reference_hz = word*laser_pll.ADC_SAMPLE_RATE_HZ/(1 << 48)
        settings = rf_settings(ol)
        if (not settings['rf_amplitude_codes']
                or abs(reference_hz-settings['rf_dac_mixer']['Freq']*1e6) > .001):
            raise ValueError('RF carrier must be on and match the receive reference; rerun setup_rf().')
    else:
        raise ValueError("mode must be 'closed' or 'rf'.")


def measure_point(ol, frequency_hz, *, mode='closed', amplitude_codes=32,
                  phase_amplitude_rad=.05, polarity=1, allow_clipping=False,
                  minimum_measure_s=1.0, minimum_settle_s=.05, measure_cycles=16):
    """One coherent block; phase in radians, closed-mode drive in DAC codes.

    Raw phase is unwrapped relative to arm, with +/-2-turn observation range.
    This diagnostic range does not alter the 24-bit feedback slip accumulator.
    Overflow/ADC rails set clipping; a missing phase or AXIS sample rejects the
    block. Optional clipping override returns a visibly flagged estimate.
    """
    if mode not in ('closed', 'rf') or polarity not in (-1, 1) or not isinstance(allow_clipping, bool):
        raise ValueError('Choose closed/rf mode, +/-1 polarity and a Boolean clipping override.')
    if mode == 'rf':
        if not math.isfinite(phase_amplitude_rad) or not .005 <= phase_amplitude_rad <= .2:
            raise ValueError('Start with 0.005..0.2 rad peak RF phase modulation (default 0.05).')
        amplitude_codes = round(phase_amplitude_rad*PHASE_CODES_PER_RAD)
    elif not isinstance(amplitude_codes, int) or not 4 <= amplitude_codes <= 32767:
        raise ValueError('Use 4..32767 integer error-output injection codes.')
    plan = fra.frequency_plan(frequency_hz, minimum_measure_s=minimum_measure_s,
                              minimum_settle_s=minimum_settle_s, measure_cycles=measure_cycles)
    _ready(ol, mode)
    configuration, settings = fra._configuration(ol), rf_settings(ol)
    tone, demods = ol.pll_fra_tone, (ol.pll_fra_error, ol.pll_fra_drive)
    try:
        tone.write(0x40, 0)
        tone.write(0x10, plan['frequency_word'])
        tone.write(0x18, polarity*amplitude_codes & 0xfffff)
        tone.write(0x20, 0)
        tone.write(0x28, 0xffffffff); tone.write(0x2c, 0xff)
        tone.write(0x34, 1); tone.write(0x38, 0)
        tone.write(0x40, 1)
        ol.pll_fra_window.write(0, plan['settle_clocks'])
        ol.pll_fra_window.write(8, plan['measure_clocks'])
        for ip in demods:
            for address in (0x14, 0x2c, 0x4c): ip.read(address)
        time.sleep(.001)
        ol.pll_fra.write(0, 5 if mode == 'closed' else 3)
        deadline = time.monotonic()+plan['duration_s']+2
        while not (status := ol.pll_fra.read(8)) & 4:
            if time.monotonic() > deadline:
                raise TimeoutError('Phase FRA integration did not complete.')
            time.sleep(.005)
        diag = fra.diagnostics(ol)
        if diag['measured_samples'] != plan['measure_clocks']:
            raise RuntimeError('Phase FRA window count mismatch.')
        if status & 0xf0 or ((status >> 8) & 3) != (2 if mode == 'closed' else 3):
            raise RuntimeError(f'Invalid phase FRA window/mode: {status:#x}, {diag}')
        clipped = bool(status & 8)
        if clipped and not allow_clipping:
            raise RuntimeError(f'Clipped phase FRA block: {diag}')
        if configuration != fra._configuration(ol) or settings != rf_settings(ol):
            raise RuntimeError('PLL or RF-source settings changed during the measurement.')
        phasors = []
        for ip in demods:
            if not ip.read(0x10) & 1 or not ip.read(0x2c) & 1 or not ip.read(0x4c) & 1:
                raise RuntimeError('Missing fresh phase FRA demodulator result.')
            phasors.append(polarity*2*complex(fra._read72(ip, 0x20), fra._read72(ip, 0x40)) /
                           (plan['measure_clocks']*32768))
        phase_rad = phasors[0]/PHASE_CODES_PER_RAD
        drive = phasors[1]/PHASE_CODES_PER_RAD if mode == 'rf' else phasors[1]
        stimulus = drive if mode == 'rf' else complex(amplitude_codes)
        if mode == 'rf' and abs(abs(stimulus)-amplitude_codes/PHASE_CODES_PER_RAD) > .02*abs(stimulus):
            raise RuntimeError('Measured transmitted PM differs from requested depth; check source/wiring.')
        return dict(**plan, mode=mode, amplitude_codes=amplitude_codes, phase_rad=phase_rad,
                    drive=drive, stimulus=stimulus, response=phase_rad/stimulus,
                    phase_amplitude_rad=amplitude_codes/PHASE_CODES_PER_RAD if mode == 'rf' else None,
                    clipped=clipped, diagnostics=diag, configuration=configuration, settings=settings)
    finally:
        stop(ol)


def sweep(ol, frequencies_hz, *, mode='closed', amplitude_codes=32, phase_amplitude_rad=.05,
          repeats=8, max_repeats=24, target_snr=30, allow_clipping=False,
          csv_path='phase_fra.csv', **window):
    """Average phasors before division; save accepted/rejected blocks and scatter.

    Response is Phi/D [rad/DAC-code] in closed mode and Phi_rx/Phi_tx [rad/rad]
    in RF mode. Closed-loop gain/sensitivity are additional columns, not an RF
    transfer function. Their reliability is checked separately when U is small.
    """
    if not isinstance(repeats, int) or not isinstance(max_repeats, int) or not 2 <= repeats <= max_repeats:
        raise ValueError('Use 2 <= repeats <= max_repeats.')
    if not math.isfinite(target_snr) or target_snr <= 0 or not isinstance(allow_clipping, bool):
        raise ValueError('Use positive target SNR and a Boolean clipping override.')
    _ready(ol, mode)
    configuration, settings = fra._configuration(ol), rf_settings(ol)
    path = Path(csv_path)
    rows, blocks = [], []
    nan = complex(float('nan'), float('nan'))
    def save(destination, records):
        with destination.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader(); writer.writerows(records)
    for frequency in frequencies_hz:
        accepted, points = [], []
        h, loop, sensitivity = nan, nan, nan
        h_sem = float('nan'); consistent = loop_reliable = False
        for attempt in range(max_repeats):
            if configuration != fra._configuration(ol) or settings != rf_settings(ol):
                raise RuntimeError('Settings changed during the phase FRA sweep.')
            point = measure_point(ol, float(frequency), mode=mode, amplitude_codes=amplitude_codes,
                                  phase_amplitude_rad=phase_amplitude_rad, polarity=1 if attempt%2 == 0 else -1,
                                  allow_clipping=True, **window)
            points.append(point)
            keep = allow_clipping or not point['clipped']
            if keep: accepted.append(point)
            phi, d, u = point['phase_rad'], point['stimulus'], point['drive']
            blocks.append(dict(mode=mode, frequency_hz=point['frequency_hz'], block=attempt,
                               accepted=keep, clipped=point['clipped'],
                               phase_re_rad=phi.real, phase_im_rad=phi.imag,
                               stimulus_re=d.real, stimulus_im=d.imag, drive_re=u.real, drive_im=u.imag,
                               **point['diagnostics']))
            save(path.with_name(path.stem+'_blocks.csv'), blocks)
            n = len(accepted)
            if n < 2: continue
            phases = np.array([p['phase_rad'] for p in accepted])
            stimuli = np.array([p['stimulus'] for p in accepted])
            drives = np.array([p['drive'] for p in accepted])
            phi, d, u = phases.mean(), stimuli.mean(), drives.mean()
            if abs(d) == 0: continue
            h = phi/d
            # Correlated numerator/denominator noise is retained in this residual.
            h_sem = float(np.std(phases-h*stimuli, ddof=1)/(math.sqrt(n)*abs(d)))
            d_sem = float(np.std(stimuli, ddof=1)/math.sqrt(n))
            consistent = bool(abs(h) > target_snr*h_sem and abs(d) > target_snr*d_sem)
            if mode == 'closed':
                loop = (d-u)/u if abs(u) > 0 else nan
                sensitivity = u/d
                u_sem = float(np.std(drives, ddof=1)/math.sqrt(n))
                loop_reliable = bool(abs(u) > target_snr*u_sem)
            if n >= repeats and consistent and (mode != 'closed' or loop_reliable): break
        clipped = any(p['clipped'] for p in accepted)
        reliable = len(accepted) >= repeats and consistent and not clipped
        row = dict(mode=mode, frequency_hz=points[0]['frequency_hz'], requested_hz=float(frequency),
                   response_units='rad/DAC-code' if mode == 'closed' else 'rad/rad',
                   response_re=h.real, response_im=h.imag, complex_sem=h_sem,
                   loop_re=loop.real, loop_im=loop.imag,
                   sensitivity_re=sensitivity.real, sensitivity_im=sensitivity.imag,
                   reliable=reliable, loop_reliable=loop_reliable and len(accepted)>=repeats and not clipped,
                   repeats=len(accepted), attempts=len(points), clipped=clipped,
                   clipped_blocks=sum(p['clipped'] for p in points),
                   amplitude_codes=points[0]['amplitude_codes'],
                   measure_s=points[0]['measure_clocks']/fra.FS_HZ)
        rows.append(row); save(path, rows)
        print(f"{row['frequency_hz']:10.3f} Hz  |H|={abs(h):.6g} {row['response_units']}  "
              f"phase={np.angle(h, deg=True):+.2f} deg  accepted={len(accepted)}/{len(points)}  reliable={reliable}")
    return rows
