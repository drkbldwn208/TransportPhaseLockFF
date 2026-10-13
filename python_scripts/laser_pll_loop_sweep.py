"""A8 closed-loop analyzer: DAC-code phasors at the digital injection point.

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
CLIPPING_FLAG = 1 << 3


def frequency_plan(frequency_hz, *, settle_cycles=5, measure_cycles=16,
                   minimum_settle_s=0.02, minimum_measure_s=0.2):
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
    return values + (ol.pll_iir.read(0), ol.pll_iir_feed.read(0), ol.pll_iir_feed.read(8),
                     ol.pll_iir_pole.read(0), ol.pll_tracking.read(0),
                     ol.pll_tracking.read(8) & 0x3FFFFFF)


def _ready(ol):
    # Jupyter can retain an older control helper after files are replaced.
    if getattr(laser_pll, 'FPGA_VERSION', None) != 0xA8:
        path = getattr(laser_pll, '__file__', '<unknown path>')
        raise RuntimeError(
            f"The sweep requires the A8 laser_pll.py; loaded {path}. "
            "Copy both A8 Python helpers to the notebook directory, then run "
            "importlib.reload(laser_pll) and importlib.reload(fra). "
            "Reloading Python does not reset the FPGA or the lock.")
    if ol.pll_acquisition_status.read(8) >> 24 != 0xA8:
        raise ValueError("The loop analyzer requires the matching A8 bitstream/HWH.")
    for name in ('pll_fra', 'pll_fra_window', 'pll_fra_tone',
                 'pll_fra_error', 'pll_fra_drive', 'pll_fra_counts', 'pll_fra_extrema',
                 'pll_fra_samples', 'pll_iir', 'pll_iir_feed', 'pll_iir_pole'):
        if not hasattr(ol, name):
            raise ValueError(f"Overlay is missing {name}; use the matching A8 HWH.")
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
    value &= (1 << 72) - 1
    return value - (1 << 72) if value & (1 << 71) else value



def diagnostics(ol):
    """Last completed window, including short events invisible on a slow scope."""
    n=ol.pll_fra_samples.read(8)
    def extrema(word):
        low,high=word & 65535,word>>16
        return (low-65536 if low & 32768 else low, high-65536 if high & 32768 else high)
    clipped=ol.pll_fra_counts.read(0)
    saturated=ol.pll_fra_counts.read(8)
    return dict(measured_samples=n, dac_clip_samples=clipped,
                detector_saturated_samples=saturated,
                dac_clip_fraction=clipped/n if n else float('nan'),
                detector_saturated_fraction=saturated/n if n else float('nan'),
                outside_clip_samples=ol.pll_fra_samples.read(0),
                error_range_codes=extrema(ol.pll_fra_extrema.read(0)),
                drive_range_codes=extrema(ol.pll_fra_extrema.read(8)))

def measure_point(ol, frequency_hz, *, amplitude_codes=32, settle_cycles=5,
                  measure_cycles=16, minimum_settle_s=0.02, minimum_measure_s=0.2,
                  allow_clipping=False, polarity=1):
    """Return simultaneous E and U peak phasors, in signed 16-bit DAC codes.

    At nominal 2 Vpp, 32 codes is approximately 0.977 mV peak. Probe amplitude
    must be checked experimentally: repeat with half amplitude to test linearity.
    allow_clipping=True retains clipped runs and sets result['clipped']; other
    hardware faults still raise. The flag covers only the integration window;
    separate counters report DAC and internal clipping, extrema and settling
    events. polarity=-1 reverses the injected sine and normalizes returned
    phasors back to the positive-probe convention. Cleanup always
    ramps down the stimulus. Clipping can bias the response even after averaging.
    """
    if not isinstance(amplitude_codes, int) or not 4 <= amplitude_codes <= 32767:
        raise ValueError("amplitude_codes must be an integer in [4, 32767].")
    if not isinstance(allow_clipping, bool):
        raise ValueError("allow_clipping must be True or False.")
    if polarity not in (-1, 1):
        raise ValueError("Probe polarity must be +1 or -1.")
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
        tone.write(0x18, (polarity*amplitude_codes) & 0xFFFFF)
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
        diag=diagnostics(ol)
        if diag["measured_samples"] != plan["measure_clocks"]:
            raise RuntimeError("FRA window count mismatch; use the matching A8 bit/HWH/helper.")
        rejected_faults = status & FAULT_MASK
        if allow_clipping:
            rejected_faults &= ~CLIPPING_FLAG
        if rejected_faults:
            names = ('clipping', 'invalid phase/DAC stall', 'monitor sample loss', 'generator gap', 'abort')
            faults = [name for k,name in enumerate(names) if rejected_faults & (1<<(k+3))]
            raise RuntimeError("Rejecting transfer measurement: "+', '.join(faults)+f"; {diag}")
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
            phasors.append(polarity*2*complex(i_sum,q_sum)/(plan['measure_clocks']*32768))
        injection=phasors[1]-phasors[0]
        excitation_ok=abs(injection-amplitude_codes)<max(1.5,0.05*amplitude_codes)
        if not status & CLIPPING_FLAG and not excitation_ok:
            raise RuntimeError(f"Measured injection {injection} does not match {amplitude_codes} codes; "
                               "check the HWH, generator and probe connections.")
        return dict(**plan, amplitude_codes=amplitude_codes, error=phasors[0], drive=phasors[1],
                    injection=injection, excitation_ok=bool(excitation_ok),
                    sums=sums, configuration=configuration, status=status, polarity=polarity, diagnostics=diag,
                    clipped=bool(status & CLIPPING_FLAG), allow_clipping=allow_clipping)
    finally:
        stop(ol)



def sweep(ol, frequencies_hz, *, amplitude_codes=32, repeats=4, max_repeats=12,
          target_snr=5.0, csv_path=None, allow_clipping=False, **window):
    """Average complex responses, extending noisy points to max_repeats.

    Each block uses >=0.2 s by default (10x the old integration). Probe sign
    alternates to reduce repeatable, injection-independent offsets; it does not
    cancel arbitrary laser noise. Compare half-amplitude runs to check linearity.
    Clipped blocks are counted and omitted unless allow_clipping=True. A point
    with no accepted blocks is saved as NaN and the sweep continues. All other
    hardware faults still stop the run. No filtering is added to the feedback.

    Error bars are repeat scatter / sqrt(N), not a model of slow drift. The
    transfer estimate is the ratio of averaged phasors, never averaged ratios.
    Inspect reliability before interpreting large L when the driven response
    approaches the disturbance floor. Every acquired block is saved to a second
    CSV (suffix _blocks) so phase-slip contamination remains inspectable.
    """
    if not isinstance(repeats,int) or repeats<2 or not isinstance(max_repeats,int) or max_repeats<repeats:
        raise ValueError("Use 2 <= repeats <= max_repeats.")
    if not math.isfinite(target_snr) or target_snr<=0:
        raise ValueError("target_snr must be positive and finite.")
    rows=[]; blocks=[]
    configuration=_configuration(ol)
    def save(path, records):
        with Path(path).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(records[0]))
            writer.writeheader(); writer.writerows(records)
    for frequency_hz in frequencies_hz:
        accepted=[]; points=[]; repeat_consistent=False
        for attempt in range(max_repeats):
            point=measure_point(ol,float(frequency_hz),amplitude_codes=amplitude_codes,
                                allow_clipping=True,polarity=1 if attempt%2==0 else -1,**window)
            if point['configuration']!=configuration:
                raise RuntimeError("PLL settings changed during this sweep.")
            points.append(point)
            keep=allow_clipping or not point['clipped']
            if keep: accepted.append(point)
            diag=point['diagnostics']
            blocks.append(dict(frequency_hz=point['frequency_hz'],block=attempt,
                               polarity=point['polarity'],accepted=keep,clipped=point['clipped'],
                               error_re=point['error'].real,error_im=point['error'].imag,
                               drive_re=point['drive'].real,drive_im=point['drive'].imag,**diag))
            if csv_path is not None:
                path=Path(csv_path)
                save(path.with_name(path.stem+'_blocks.csv'),blocks)
            n=len(accepted)
            if n<2: continue
            errors=np.array([p['error'] for p in accepted]); drives=np.array([p['drive'] for p in accepted])
            e,u=errors.mean(),drives.mean()
            e_sem=float(np.std(errors,ddof=1)/np.sqrt(n))
            u_sem=float(np.std(drives,ddof=1)/np.sqrt(n))
            repeat_consistent=bool(abs(e)>target_snr*e_sem and abs(u)>target_snr*u_sem
                                   and abs((u-e)-amplitude_codes)<max(1.5,0.05*amplitude_codes))
            if n>=repeats and repeat_consistent: break
        n=len(accepted)
        nan=complex(float('nan'),float('nan'))
        if n<2:
            e=u=nan; e_sem=u_sem=float('nan'); repeat_consistent=False
        d=u-e
        loop=-e/u if abs(u)>0 else nan
        sensitivity=u/d if abs(d)>0 else nan
        clipped_repeats=sum(p['clipped'] for p in points)
        accepted_clipping=any(p['clipped'] for p in accepted)
        row=dict(requested_hz=float(frequency_hz),frequency_hz=points[0]['frequency_hz'],
                 amplitude_codes=amplitude_codes,repeats=n,attempts=len(points),
                 allow_clipping=allow_clipping,clipped=accepted_clipping,
                 clipped_repeats=clipped_repeats,
                 settle_s=points[0]['settle_clocks']/FS_HZ,measure_s=points[0]['measure_clocks']/FS_HZ,
                 measure_clocks=points[0]['measure_clocks'],pll_control_word=configuration[0],
                 acquisition_word=configuration[4],tracking_coefficient=configuration[-1],
                 iir_control_word=configuration[6],iir_b0_word=configuration[7],
                 iir_b1_word=configuration[8],iir_pole_word=configuration[9],
                 error_re=float(e.real),error_im=float(e.imag),drive_re=float(u.real),drive_im=float(u.imag),
                 injection_re=float(d.real),injection_im=float(d.imag),
                 loop_re=float(loop.real),loop_im=float(loop.imag),
                 sensitivity_re=float(sensitivity.real),sensitivity_im=float(sensitivity.imag),
                 error_stderr_codes=e_sem,drive_stderr_codes=u_sem,
                 dac_clip_samples=sum(p['diagnostics']['dac_clip_samples'] for p in points),
                 detector_saturated_samples=sum(p['diagnostics']['detector_saturated_samples'] for p in points),
                 outside_clip_samples=sum(p['diagnostics']['outside_clip_samples'] for p in points),
                 repeat_consistent=repeat_consistent,
                 reliable=repeat_consistent and n>=repeats and not accepted_clipping)
        rows.append(row)
        if csv_path is not None: save(csv_path,rows)
        print(f"{row['frequency_hz']:10.3f} Hz  |L|={abs(loop):9.3g}  "
              f"phase={np.angle(loop,deg=True):8.2f} deg  accepted={n}/{len(points)}  "
              f"reliable={row['reliable']}  clipped blocks={clipped_repeats}")
    return rows
