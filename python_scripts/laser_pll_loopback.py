"""A8 coherent DAC229/1 -> ADC224/3 loopback response, 10 Hz .. 5 MHz.

Both RF direct and external-mixer tests use the existing fabric mixer/FIR receiver.
No laser controller should be connected to the stimulated DAC during this test.
All phasors use peak sine amplitudes and exp(+j*phase): a delay has negative phase.
"""
import csv
import math
import time
from pathlib import Path

import numpy as np
import laser_pll
import laser_pll_loop_sweep as fra

FS_HZ = 245_760_000.0
HELPER_REVISION = 2  # Python-only voltage bounds and dependency preflight; same A8 FPGA.


def check_helpers(ol):
    """Reject stale/cached dependencies before changing any output registers."""
    required = ('diagnostics', '_configuration', '_read72', 'stop')
    if (getattr(fra, 'FPGA_VERSION', None) != 0xA8
            or any(not callable(getattr(fra, name, None)) for name in required)
            or getattr(fra, 'laser_pll', None) is not laser_pll):
        raise RuntimeError(
            f"Stale or mismatched sweep helper: {getattr(fra, '__file__', '<unknown>')}. "
            "Copy all three current A8 .py files together, reload laser_pll, "
            "laser_pll_loop_sweep and laser_pll_loopback, and rebind fra.laser_pll, "
            "lb.laser_pll and lb.fra. No stimulus has been applied by this call.")
    if getattr(laser_pll, 'FPGA_VERSION', None) != 0xA8 or ol.pll_acquisition_status.read(8) >> 24 != 0xA8:
        raise ValueError('Use the matching A8 bit/HWH and laser_pll.py helper.')
    for name in ('pll_loopback_i', 'pll_loopback_q'):
        if not hasattr(ol, name):
            raise ValueError(f'Missing {name}; load the A8 HWH.')


def voltage_limits(voltage_at_zero_V, voltage_at_test_V, *, test_codes=100,
                   maximum_abs_V=0.100, margin_V=0.020):
    """D2S voltage model from two meter readings, with the mixer IF disconnected.

    Measure at the D2S output, preferably high impedance to bound the unloaded
    voltage. V(code) = offset_V + volts_per_code*code. Margin allows offset drift
    and modest AC peaking; it is not a hardware clamp or a measurement of either.
    Recheck after changing gain, RFDC settings, cabling or termination.
    """
    if not isinstance(test_codes, int) or not 0 < abs(test_codes) <= 32767:
        raise ValueError('Use a nonzero integer calibration code within the DAC range.')
    limits = dict(volts_per_code=(voltage_at_test_V-voltage_at_zero_V)/test_codes,
                  offset_V=voltage_at_zero_V, maximum_abs_V=maximum_abs_V, margin_V=margin_V)
    check_output(0, 0, limits)
    check_output(test_codes, 0, limits)
    return limits


def check_output(bias_codes, amplitude_codes, output_limits):
    """Check the entire bias +/- peak-amplitude interval before writing hardware.

    Returns predicted maximum absolute D2S voltage, or None for direct RF mode.
    The fixed 100 mV ceiling applies to the D2S waveform including calibration.
    """
    if abs(bias_codes)+amplitude_codes > 32760:
        raise ValueError('DC bias plus probe would clip the DAC.')
    if output_limits is None:
        return None
    slope, offset, maximum, margin = (output_limits[k] for k in
                                    ('volts_per_code', 'offset_V', 'maximum_abs_V', 'margin_V'))
    if (not all(math.isfinite(v) for v in (slope, offset, maximum, margin))
            or slope == 0 or not 0 <= margin < maximum <= .100):
        raise ValueError('Use finite measured volts/code and offset; 0 <= margin < limit <= 0.100 V.')
    peak_V = abs(offset+slope*bias_codes)+abs(slope)*amplitude_codes
    if peak_V+margin >= maximum:
        raise ValueError(f'D2S output could reach {1e3*peak_V:.2f} mV, plus '
                         f'{1e3*margin:g} mV margin; limit is {1e3*maximum:g} mV. '
                         'Reduce bias, amplitude or calibration step.')
    return peak_V


def _output_limits(ol):
    setup_info = getattr(ol, '_laser_pll_loopback_setup', None)
    if setup_info is None:
        raise ValueError('Call the current setup() first; mixer mode requires measured output_limits.')
    if receiver_settings(ol) != setup_info['receiver_settings']:
        raise ValueError('Converter/LO settings changed; recheck D2S voltage and rerun setup().')
    return setup_info['output_limits']


def receiver_settings(ol):
    """Read the existing beat-note ADC and TP LO; frequencies are in MHz."""
    rf = ol.usp_rf_data_converter_0
    return dict(adc_mixer=dict(rf.adc_tiles[0].blocks[3].MixerSettings),
                tp_lo_mixer=dict(rf.dac_tiles[0].blocks[1].MixerSettings),
                stimulus_mixer=dict(rf.dac_tiles[1].blocks[1].MixerSettings),
                tp_lo_amplitude_codes=ol.axi_gpio_12.read(0) & 65535)


def setup(ol, *, mode, carrier_hz=90e6, bias_codes=0, output_limits=None):
    """Select DAC229/1 DC-test mode and its NCO; preserve RFDC ADC/TP-LO settings.

    mode='rf': DAC229/1 RF directly into ADC224/3.
    mode='mixer': DAC229/1 near-DC -> mixer IF, existing TP LO -> LO,
                  mixer RF -> ADC224/3. DAC228/1 TP LO is configured by the user.
    Keeps both converter rates and all decimation/interpolation factors intact.
    Returns the prior DAC mixer settings for documentation; does not restore a
    previous live feedback state automatically.
    Mixer mode requires output_limits from measured D2S volts/code and offset.
    """
    check_helpers(ol)
    if mode not in ('rf', 'mixer'):
        raise ValueError("mode must be 'rf' or 'mixer'.")
    if not isinstance(bias_codes, int) or not -30000 <= bias_codes <= 30000:
        raise ValueError('Use an integer DC bias within +/-30000 DAC codes.')
    if mode == 'mixer' and output_limits is None:
        raise ValueError('Mixer mode requires output_limits from voltage_limits(); '
                         'measure the D2S output with mixer IF disconnected first.')
    check_output(0, 0, output_limits)  # Muting/startup also passes through zero code.
    check_output(bias_codes, 0, output_limits)
    if not math.isfinite(carrier_hz) or not 1e6 <= carrier_hz < laser_pll.ADC_SAMPLE_RATE_HZ/2 or (mode == 'mixer' and carrier_hz > 450e6):
        raise ValueError('Use a zone-1 carrier; keep the ZAD-1+ test below 450 MHz. Use 90 MHz for a matched comparison.')
    params = ol.ip_dict['usp_rf_data_converter_0']['parameters']
    for key, expected in [('ADC_Decimation_Mode03', 1), ('ADC_Data_Type03', 0),
                          ('DAC_Interpolation_Mode11', 4)]:
        if int(params[key]) != expected:
            raise ValueError(f'Unexpected converter configuration: {key}.')
    settings = receiver_settings(ol)
    if mode == 'mixer' and (abs(settings['tp_lo_mixer']['Freq']*1e6-carrier_hz) > 1
                           or settings['tp_lo_amplitude_codes'] == 0):
        raise ValueError('Configure the TP LO at the same carrier and nonzero amplitude first.')
    import xrfdc
    fra.stop(ol)
    laser_pll.enable(ol, False)
    ol.pll_iir.write(0, ol.pll_iir.read(0) & ~1)
    dac = ol.usp_rf_data_converter_0.dac_tiles[1].blocks[1]
    cfg = dict(dac.MixerSettings)
    cfg.update(Freq=carrier_hz/1e6 if mode == 'rf' else 0.0, PhaseOffset=0.0,
               EventSource=xrfdc.EVNT_SRC_IMMEDIATE, MixerType=xrfdc.MIXER_TYPE_FINE,
               MixerMode=xrfdc.MIXER_MODE_C2R, FineMixerScale=xrfdc.MIXER_SCALE_1P0)
    dac.MixerSettings = cfg
    dac.ResetNCOPhase()
    dac.UpdateEvent(xrfdc.EVENT_MIXER)
    laser_pll.set_reference_frequency(ol, carrier_hz, restart_phase=True)
    laser_pll.set_dc_output(ol, bias_codes)
    laser_pll.enable(ol)
    _wait_dc(ol)
    setup_info = dict(mode=mode, carrier_hz=carrier_hz, bias_codes=bias_codes,
                      output_limits=dict(output_limits) if output_limits is not None else None,
                      receiver_settings=receiver_settings(ol), previous_settings=settings)
    ol._laser_pll_loopback_setup = setup_info
    return setup_info


def _wait_dc(ol):
    deadline = time.monotonic()+2
    while True:
        state = laser_pll.acquisition_status(ol)
        if state['stage'] == 5 and state['output_valid'] and not state['transitioning']:
            return
        if time.monotonic() > deadline:
            raise TimeoutError('DC-test handoff did not settle.')
        time.sleep(.002)


def stop(ol, *, mute=False):
    """Ramp down the probe, retaining the DC bias; mute=True also disables DAC229/1."""
    fra.stop(ol)
    if mute:
        laser_pll.enable(ol, False)


def frequency_plan(frequency_hz, *, minimum_measure_s=1.0, minimum_settle_s=.05, measure_cycles=16):
    if not math.isfinite(frequency_hz) or not 10 <= frequency_hz <= 5e6:
        raise ValueError('Frequency must lie in 10 Hz .. 5 MHz.')
    if not .001 <= minimum_measure_s <= 15 or not 0 <= minimum_settle_s <= 15 or measure_cycles < 1:
        raise ValueError('Use 1 ms .. 15 s integration, 0 .. 15 s settling and >=1 cycle.')
    word = round(frequency_hz*2**32/(8*FS_HZ))
    actual = word*8*FS_HZ/2**32
    cycles = math.ceil(max(measure_cycles, minimum_measure_s*actual))
    n = round(cycles*FS_HZ/actual)
    settle = math.ceil(max(minimum_settle_s, 5/actual)*FS_HZ)
    if max(n, settle) >= 2**32:
        raise ValueError('Window exceeds the 32-bit hardware counter.')
    return dict(frequency_hz=actual, requested_hz=float(frequency_hz), frequency_word=word,
                measure_clocks=n, settle_clocks=settle, integration_s=n/FS_HZ,
                duration_s=(n+settle)/FS_HZ+2*fra.RAMP_TIME_S)


def _signed64_gpio(ip):
    value = (ip.read(0) & 0xffffffff) | ((ip.read(8) & 0xffffffff) << 32)
    return value-(1 << 64) if value & (1 << 63) else value


def measure_point(ol, frequency_hz, *, amplitude_codes=32, polarity=1, **window):
    """Return I/Q response and DC means, in post-mixer ADC counts (not calibrated volts).

    Every fabric beat is synchronously demodulated BEFORE the long boxcar
    integration/decimation. This retains a 1 MHz probe while averaging down noise.
    Zero amplitude is allowed only for DC calibration; IQ phasors then have no
    driven-response interpretation. Receiver rail counts monitor the raw ADC lanes within 16 codes of either
    rail; clipping in an external analog stage still requires a linearity check.
    """
    check_helpers(ol)
    if not isinstance(amplitude_codes, int) or not 0 <= amplitude_codes <= 16000 or polarity not in (-1, 1):
        raise ValueError('Use 0..16000 integer amplitude codes and polarity +/-1.')
    state = laser_pll.acquisition_status(ol)
    if state['stage'] != 5 or state['transitioning'] or not state['output_valid'] or not ol.pll_control.read(0) & 1:
        raise ValueError('Call setup() and wait for enabled DC mode first.')
    if ol.pll_iir.read(0) & 1 or ol.pll_fra.read(0) & 1 or ol.pll_fra.read(8) & 1:
        raise ValueError('Select IIR bypass and stop the previous FRA run.')
    bias = ol.pll_acquisition.read(8) & 65535
    bias = bias-65536 if bias & 32768 else bias
    peak_V = check_output(bias, amplitude_codes, _output_limits(ol))
    plan = frequency_plan(frequency_hz, **window)
    configuration = fra._configuration(ol)
    settings = receiver_settings(ol)
    tone = ol.pll_fra_tone
    demods = (ol.pll_fra_error, ol.pll_fra_drive)
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
            for offset in (0x14, 0x2c, 0x4c): ip.read(offset)
        time.sleep(.001)
        ol.pll_fra.write(0, 3)  # arm + intensity I/Q observations
        deadline = time.monotonic()+plan['duration_s']+2
        while not (status := ol.pll_fra.read(8)) & 4:
            if time.monotonic() > deadline:
                raise TimeoutError('Loopback integration did not complete.')
            time.sleep(.005)
        diag = fra.diagnostics(ol)
        diag['receiver_rail_samples'] = diag.pop('detector_saturated_samples')
        diag['receiver_rail_fraction'] = diag.pop('detector_saturated_fraction')
        if status & 0xf8 or diag['measured_samples'] != plan['measure_clocks']:
            raise RuntimeError(f'Invalid loopback window: status={status:#x}, {diag}')
        if fra._configuration(ol) != configuration or receiver_settings(ol) != settings:
            raise RuntimeError('Configuration changed during the measurement.')
        phasors = []
        n = plan['measure_clocks']
        for ip in demods:
            if not ip.read(0x10) & 1 or not ip.read(0x2c) & 1 or not ip.read(0x4c) & 1:
                raise RuntimeError('Missing fresh demodulator result.')
            phasors.append(polarity*2*complex(fra._read72(ip, 0x20), fra._read72(ip, 0x40))/(n*32768*4))
        means = [_signed64_gpio(ip)/(n*4) for ip in (ol.pll_loopback_i, ol.pll_loopback_q)]
        return dict(**plan, amplitude_codes=amplitude_codes, bias_codes=bias, polarity=polarity,
                    i=phasors[0], q=phasors[1], mean_i=means[0], mean_q=means[1], diagnostics=diag,
                    predicted_peak_V=peak_V)
    finally:
        stop(ol)


def calibrate(ol, *, step_codes=32, integration_s=1.0):
    """Measure the real DC response vector using two bias levels around the operating point.

    Subtracting the means removes fixed mixer LO leakage/receiver offsets.
    Normalizing against this vector gives H(0)=1 including physical polarity.
    Both levels must remain in the mixer/converter linear range. Inspect the
    returned slope magnitude; repeat calibration to check drift or frequency mismatch.
    """
    check_helpers(ol)
    bias = ol.pll_acquisition.read(8) & 65535
    bias = bias-65536 if bias & 32768 else bias
    if not isinstance(step_codes, int) or not 1 <= step_codes or abs(bias)+step_codes > 30000:
        raise ValueError('Calibration step exceeds the DAC bias range.')
    check_output(bias, step_codes, _output_limits(ol))
    frequency_plan(1000, minimum_measure_s=integration_s)
    state = laser_pll.acquisition_status(ol)
    if state['stage'] != 5 or state['transitioning'] or not ol.pll_control.read(0) & 1:
        raise ValueError('Call setup() before calibration.')
    if ol.pll_fra.read(0) & 1 or ol.pll_fra.read(8) & 1:
        raise ValueError('Stop the previous FRA run before changing the calibration bias.')
    points = []
    try:
        for code in (bias-step_codes, bias+step_codes, bias-step_codes):
            laser_pll.set_dc_output(ol, code)
            time.sleep(.05)
            points.append(measure_point(ol, 1000, amplitude_codes=0, minimum_measure_s=integration_s))
    finally:
        laser_pll.set_dc_output(ol, bias)
        time.sleep(.05)
    low_i = (points[0]['mean_i']+points[2]['mean_i'])/2
    low_q = (points[0]['mean_q']+points[2]['mean_q'])/2
    gi = (points[1]['mean_i']-low_i)/(2*step_codes)
    gq = (points[1]['mean_q']-low_q)/(2*step_codes)
    if math.hypot(gi, gq) < 1e-5:
        raise RuntimeError('No DC response: check connections, LO, carrier mismatch or DC blocking.')
    drift_fraction = math.hypot(points[2]['mean_i']-points[0]['mean_i'],
                                points[2]['mean_q']-points[0]['mean_q'])/(2*step_codes*math.hypot(gi, gq))
    if drift_fraction > .05:
        raise RuntimeError(f'DC calibration drifted by {drift_fraction:.1%} of the step response. '
                           'Check carrier/NCO frequency matching and increase integration for a weak signal.')
    return dict(gain_i=gi, gain_q=gq, bias_codes=bias, step_codes=step_codes, drift_fraction=drift_fraction,
                points=points, receiver_settings=receiver_settings(ol))


def project(point, calibration):
    """DC-normalized response along the received carrier and its orthogonal component."""
    gi, gq = calibration['gain_i'], calibration['gain_q']
    norm = (gi*gi+gq*gq)*point['amplitude_codes']
    if norm == 0:
        raise ValueError('A nonzero drive and calibration vector are required.')
    return ((gi*point['i']+gq*point['q'])/norm,
            (-gq*point['i']+gi*point['q'])/norm)


def sweep(ol, frequencies_hz, calibration, *, amplitude_codes=32, repeats=8,
          max_repeats=24, target_snr=30.0, csv_path='loopback.csv', **window):
    """Complex averaging with alternating probe sign, uncertainty, and incremental CSVs.

    Default >=1 s per block, >=8 blocks/point: >=1.97 billion fabric observations
    per frequency. Increase max_repeats or integration for weak returns. A point
    that misses target_snr is retained with reliable=False, never silently smoothed.
    Scatter/sqrt(N) quantifies random repeat noise, not systematic drift/distortion.
    """
    if not isinstance(repeats, int) or repeats < 2 or repeats % 2 or not isinstance(max_repeats, int) or max_repeats < repeats or max_repeats % 2:
        raise ValueError('Use even repeat counts with 2 <= repeats <= max_repeats.')
    if not math.isfinite(target_snr) or target_snr <= 0 or amplitude_codes <= 0:
        raise ValueError('Positive SNR target and probe amplitude required.')
    rows, blocks = [], []
    def save(path, records):
        with Path(path).open('w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(records[0]))
            writer.writeheader(); writer.writerows(records)
    path = Path(csv_path)
    for frequency in frequencies_hz:
        hs, cross = [], []
        for k in range(max_repeats):
            if receiver_settings(ol) != calibration['receiver_settings'] or (ol.pll_acquisition.read(8) & 65535) != (calibration['bias_codes'] & 65535):
                raise RuntimeError('Receiver/LO/DAC settings or DC bias changed since calibration.')
            point = measure_point(ol, float(frequency), amplitude_codes=amplitude_codes, polarity=1 if k % 2 == 0 else -1, **window)
            h, perpendicular = project(point, calibration)
            hs.append(h); cross.append(perpendicular)
            blocks.append(dict(frequency_hz=point['frequency_hz'], repeat=k, polarity=point['polarity'],
                               integration_s=point['integration_s'], amplitude_codes=amplitude_codes,
                               i_real=point['i'].real, i_imag=point['i'].imag,
                               q_real=point['q'].real, q_imag=point['q'].imag,
                               mean_i=point['mean_i'], mean_q=point['mean_q'],
                               h_real=h.real, h_imag=h.imag))
            save(path.with_name(path.stem+'_blocks.csv'), blocks)
            mean = np.mean(hs)
            sem = np.std(hs, ddof=1)/math.sqrt(len(hs)) if len(hs)>1 else float('inf')
            snr = abs(mean)/max(sem, 1e-30)
            if k+1 >= repeats and (k+1) % 2 == 0 and snr >= target_snr:
                break
        perp = np.mean(cross)
        row = dict(frequency_hz=point['frequency_hz'], h_real=mean.real, h_imag=mean.imag,
                   magnitude_db=20*np.log10(max(abs(mean), 1e-30)), phase_deg=np.angle(mean, deg=True),
                   complex_sem=float(sem), snr=float(snr), repeats=len(hs), reliable=bool(snr >= target_snr),
                   perpendicular_real=perp.real, perpendicular_imag=perp.imag,
                   integration_s=point['integration_s'], amplitude_codes=amplitude_codes)
        rows.append(row); save(path, rows)
        print(f"{row['frequency_hz']:10.3f} Hz  {row['magnitude_db']:+8.3f} dB  "
              f"{row['phase_deg']:+8.2f} deg  SNR={snr:.1f}  N={len(hs)}")
    return rows


def fit_delay(rows, *, minimum_hz=10000, maximum_hz=1e6):
    """Weighted phase-line fit with free intercept; curvature means frequency-dependent delay.

    Includes the existing fabric mixer/FIR receiver plus the full converter path.
    No automatic de-embedding. Frequency spacing must resolve phase wraps.
    """
    selected = sorted((r for r in rows if r['reliable'] and minimum_hz <= r['frequency_hz'] <= maximum_hz), key=lambda r:r['frequency_hz'])
    if len(selected) < 3:
        raise ValueError('Need at least three reliable points in the delay-fit band.')
    frequency = np.array([r['frequency_hz'] for r in selected])
    h = np.array([complex(r['h_real'],r['h_imag']) for r in selected])
    phase = np.unwrap(np.angle(h))
    phase_sigma = np.array([max(r['complex_sem']/abs(z), 1e-5) for r,z in zip(selected,h)])
    slope, intercept = np.polyfit(frequency, phase, 1, w=1/phase_sigma)
    residual = phase-(slope*frequency+intercept)
    return dict(delay_s=-slope/(2*np.pi), intercept_rad=intercept,
                phase_residual_rms_rad=float(np.sqrt(np.mean(residual**2))),
                frequency_hz=frequency, phase_rad=phase, fit_rad=slope*frequency+intercept)
