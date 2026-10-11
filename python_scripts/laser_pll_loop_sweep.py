"""A6 closed-loop analyzer: DAC-code phasors at the digital injection point.

e = original discriminator output, d = injected sine, u = e+d = DAC command.
The negative-feedback convention is e = -L*u, so L=-E/U, S=U/(U-E).
This includes both analog branches, laser, converters and active discriminator.
Measurements require an already locked, stationary loop; no lock controls change.
"""
import csv
import math
import time
from pathlib import Path

import numpy as np
import laser_pll

FS_HZ = laser_pll.ERROR_SAMPLE_RATE_HZ
RAMP_TIME_S = 4096 * 64 / FS_HZ
FAULT_MASK = 0xF8


def frequency_plan(frequency_hz, *, settle_cycles=5, measure_cycles=16,
                   minimum_settle_s=0.02, minimum_measure_s=0.02):
    """Quantize the old eight-lane DDS and use approximately whole-cycle windows."""
    if not math.isfinite(frequency_hz) or not 10 <= frequency_hz <= 1e6:
        raise ValueError("Sweep frequency must be between 10 Hz and 1 MHz.")
    for value in (settle_cycles, measure_cycles, minimum_settle_s, minimum_measure_s):
        if not math.isfinite(value) or value < 0:
            raise ValueError("Cycle counts and minimum times must be finite and nonnegative.")
    if measure_cycles < 1:
        raise ValueError("Integrate at least one cycle.")
    word = round(frequency_hz * 2**32 / (8 * FS_HZ))
    actual_hz = word * (8 * FS_HZ) / 2**32
    cycles = math.ceil(max(measure_cycles, minimum_measure_s * actual_hz))
    n_measure = round(cycles * FS_HZ / actual_hz)
    n_settle = max(16, math.ceil(max(minimum_settle_s, settle_cycles / actual_hz) * FS_HZ))
    if not 1 <= n_measure < 2**32 or not 0 <= n_settle < 2**32:
        raise ValueError("Each settling/integration interval must fit a 32-bit clock count (17.48 s).")
    return dict(requested_hz=float(frequency_hz), frequency_hz=actual_hz, frequency_word=word,
                measure_cycles=cycles, measure_clocks=n_measure, settle_clocks=n_settle,
                duration_s=(n_measure+n_settle)/FS_HZ+2*RAMP_TIME_S)


def _configuration(ol):
    """Registers that must remain fixed during a linear-response measurement."""
    registers = (ol.pll_control, ol.pll_frequency, ol.pll_acquisition)
    values = tuple(ip.read(offset) for ip in registers for offset in (0, 8))
    # Exclude transient valid/saturation flags, retain the actual tracking slope.
    return values + (ol.pll_tracking.read(0), ol.pll_tracking.read(8) & 0x3FFFFFF)


def _ready(ol):
    laser_pll._check_version(ol)
    if ol.pll_acquisition_status.read(8) >> 24 != 0xA6:
        raise ValueError("The loop analyzer requires the matching A6 bitstream/HWH.")
    state = laser_pll.acquisition_status(ol)
    if not ol.pll_control.read(0) & 1 or state['stage'] not in (0, 2, 3, 4):
        raise ValueError("Enable and lock a fine detector stage before measuring.")
    if state['pending'] or state['transitioning'] or not state['output_valid']:
        raise ValueError("Wait for valid data and a settled stage handoff.")
    if state['stage']==4 and laser_pll.tracking_status(ol)['ramping']:
        raise ValueError("Wait for the tracking-gain ramp to finish.")
    if ol.pll_fra.read(8) & 1 or ol.pll_fra.read(0) & 1:
        raise ValueError("An analyzer run is already armed; call stop(ol) first.")


def stop(ol, timeout_s=0.25):
    """Ramp only the test tone to zero; leave the laser feedback state intact."""
    ol.pll_fra.write(0, 0)
    deadline = time.monotonic()+timeout_s
    while ol.pll_fra.read(8) & 1:
        if time.monotonic()>deadline:
            raise TimeoutError("Test-tone ramp did not finish; check the RF clock/reset.")
        time.sleep(0.001)
    ol.pll_fra_tone.write(0x18, 0)
    ol.pll_fra_tone.write(0x40, 0)


def _read72(ip, address):
    value = sum((ip.read(address+4*k) & 0xFFFFFFFF) << (32*k) for k in range(3))
    return laser_pll._signed(value, 72)


def measure_point(ol, frequency_hz, *, amplitude_codes=32, settle_cycles=5,
                  measure_cycles=16, minimum_settle_s=0.02, minimum_measure_s=0.02):
    """Return simultaneous E and U peak phasors, in signed 16-bit DAC codes.

    At nominal 2 Vpp, 32 codes is approximately 0.977 mV peak. Probe amplitude
    must be checked experimentally: repeat with half amplitude to test linearity.
    Hardware faults raise an exception; finally always ramps down the stimulus.
    """
    if not isinstance(amplitude_codes, int) or not 4 <= amplitude_codes <= 32767:
        raise ValueError("amplitude_codes must be an integer in [4, 32767].")
    plan = frequency_plan(frequency_hz, settle_cycles=settle_cycles,
                          measure_cycles=measure_cycles, minimum_settle_s=minimum_settle_s,
                          minimum_measure_s=minimum_measure_s)
    _ready(ol)
    configuration = _configuration(ol)
    tone = ol.pll_fra_tone
    demods = (ol.pll_fra_error, ol.pll_fra_drive)
    try:
        # The legacy generator freezes in IDLE. Keep it in SETTLING for >1 hour
        # so its phase keeps advancing through our independent ramp-down window.
        tone.write(0x40, 0)
        tone.write(0x10, plan['frequency_word'])
        tone.write(0x18, amplitude_codes)
        tone.write(0x20, 0)
        tone.write(0x28, 0xFFFFFFFF); tone.write(0x2C, 0xFF)
        tone.write(0x34, 1); tone.write(0x38, 0)
        tone.write(0x40, 1)
        ol.pll_fra_window.write(0, plan['settle_clocks'])
        ol.pll_fra_window.write(8, plan['measure_clocks'])
        # Clear stale result-valid flags. Results are latched until the next run.
        for ip in demods:
            for offset in (0x14, 0x2C, 0x4C): ip.read(offset)
        time.sleep(0.001)
        ol.pll_fra.write(0, 1)
        deadline = time.monotonic()+plan['duration_s']+1.0
        while True:
            status = ol.pll_fra.read(8)
            if status & 4: break
            if time.monotonic()>deadline:
                raise TimeoutError("Analyzer did not complete its integration window.")
            time.sleep(0.002)
        if status & FAULT_MASK:
            names = ('clipping', 'invalid phase/DAC stall', 'monitor sample loss', 'generator gap', 'abort')
            faults = [name for k,name in enumerate(names) if status & (1<<(k+3))]
            raise RuntimeError("Rejecting transfer measurement: "+', '.join(faults))
        if _configuration(ol)!=configuration:
            raise RuntimeError("PLL settings changed during the measurement; result is invalid.")
        phasors=[]
        sums=[]
        for ip in demods:
            if not ip.read(0x10) & 1 or not ip.read(0x2C) & 1 or not ip.read(0x4C) & 1:
                raise RuntimeError("Demodulator did not latch a fresh complete result.")
            i_sum, q_sum = _read72(ip,0x20), _read72(ip,0x40)
            sums.append((i_sum,q_sum))
            # Existing demod: I=sum(x*sin), Q=sum(x*cos). I+jQ has the phase
            # of x relative to the injected sine; no conjugation is needed.
            phasors.append(2*complex(i_sum,q_sum)/(plan['measure_clocks']*32768))
        return dict(**plan, amplitude_codes=amplitude_codes, error=phasors[0], drive=phasors[1],
                    sums=sums, configuration=configuration, status=status)
    finally:
        stop(ol)


def sweep(ol, frequencies_hz, *, amplitude_codes=32, repeats=3, csv_path=None, **window):
    """Measure repeated phasors; optionally checkpoint each frequency to CSV.

    Relative repeat scatter is a measurement diagnostic, not proof of optical lock.
    At high loop gain U is small: inspect drive_stderr_codes and reliable before
    trusting -E/U. The estimate includes the active discriminator, not a separately
    calibrated ADC/DAC voltage transfer. Keep analog filter settings fixed per sweep.
    """
    if not isinstance(repeats,int) or repeats<2:
        raise ValueError("Use at least two repeats to estimate measurement scatter.")
    rows=[]
    configuration=_configuration(ol)
    for frequency_hz in frequencies_hz:
        points=[measure_point(ol,float(frequency_hz),amplitude_codes=amplitude_codes,**window)
                for _ in range(repeats)]
        if any(p['configuration']!=configuration for p in points):
            raise RuntimeError("PLL settings changed during this sweep.")
        error=np.array([p['error'] for p in points]); drive=np.array([p['drive'] for p in points])
        e,u=error.mean(),drive.mean()
        d=u-e
        e_sem=float(np.std(error,ddof=1)/np.sqrt(repeats))
        u_sem=float(np.std(drive,ddof=1)/np.sqrt(repeats))
        loop=-e/u if abs(u)>0 else complex(float('nan'),float('nan'))
        sensitivity=u/d if abs(d)>0 else complex(float('nan'),float('nan'))
        row=dict(requested_hz=float(frequency_hz),frequency_hz=points[0]['frequency_hz'],
                 amplitude_codes=amplitude_codes,repeats=repeats,
                 settle_s=points[0]['settle_clocks']/FS_HZ,measure_s=points[0]['measure_clocks']/FS_HZ,
                 measure_clocks=points[0]['measure_clocks'],pll_control_word=configuration[0],
                 acquisition_word=configuration[4],tracking_coefficient=configuration[-1],
                 error_re=float(e.real),error_im=float(e.imag),drive_re=float(u.real),drive_im=float(u.imag),
                 injection_re=float(d.real),injection_im=float(d.imag),
                 loop_re=float(loop.real),loop_im=float(loop.imag),
                 sensitivity_re=float(sensitivity.real),sensitivity_im=float(sensitivity.imag),
                 error_stderr_codes=e_sem,drive_stderr_codes=u_sem,
                 reliable=bool(abs(u)>5*u_sem and abs(e)>5*e_sem and abs(d)>0))
        rows.append(row)
        if csv_path is not None:
            path=Path(csv_path)
            with path.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(row))
                writer.writeheader(); writer.writerows(rows)
        print(f"{row['frequency_hz']:10.3f} Hz  |L|={abs(loop):9.3g}  "
              f"phase={np.angle(loop,deg=True):8.2f} deg  repeat check={row['reliable']}")
    return rows
