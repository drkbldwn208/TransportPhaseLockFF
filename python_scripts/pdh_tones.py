"""Tunable summed carrier + modulation EOM drive and coherent, phase-adjustable 60 MHz LO.

DAC230/0 (tile 2 block 0): fourteen real samples/clock, RFDC x2, mixer bypass.
DAC228/2 (tile 0 block 2): eight real samples/clock, RFDC mixer bypass.
Amplitudes are fractions of signed digital full scale, NOT calibrated volts.
Two 48-bit phase accumulators; FCW slews by 1024 counts per 245.76 MHz clock.
"""
import math
import time

FEATURE_VERSION = 0x50444803
HELPER_VERSION = '2026-11-23.1'
# Reset defaults, not live frequency readbacks. Use status() for targets/ramp flags.
CARRIER_HZ = 1.2e9
MODULATION_HZ = 60e6
FABRIC_CLOCK_HZ = 245.76e6
DDS_SAMPLE_RATE_HZ = 14 * FABRIC_CLOCK_HZ
SLEW_STEP = 1024
SLEW_HZ_PER_S = SLEW_STEP * DDS_SAMPLE_RATE_HZ / 2**48 * FABRIC_CLOCK_HZ
# beta_PDH / beta_offset at their ideal PDH-slope maxima; assumes equal Vpi
# and RF voltage transfer at 60 MHz and 1.2 GHz. Calibrate on the optical setup.
DEFAULT_SIDEBAND_RATIO = 1.081979112658792 / 1.8411848682178047


def check(ol):
    if not hasattr(ol, 'pdh_version') or ol.pdh_version.read(0) != FEATURE_VERSION:
        raise ValueError('Load the matching PDH bitstream/HWH and pdh_tones.py helper.')
    if not all(hasattr(ol, name) for name in ('pdh_carrier_frequency', 'pdh_modulation_frequency')):
        raise ValueError('PDH3 frequency GPIOs are absent from the HWH; copy the matching bit/HWH pair.')
    parameters = ol.ip_dict['usp_rf_data_converter_0']['parameters']
    for name, expected in {'DAC_Data_Width20':14, 'DAC_Interpolation_Mode20':2,
                           'DAC2_Clock_Source':5,
                           'DAC_Data_Width02':8, 'DAC_Interpolation_Mode02':2}.items():
        if int(parameters[name]) != expected:
            raise ValueError(f'{name} must be {expected} for this waveform generator.')
    for name, expected in {'DAC0_Sampling_Rate':3.93216, 'DAC2_Sampling_Rate':6.88128}.items():
        if abs(float(parameters[name])-expected) > 1e-9:
            raise ValueError(f'{name} must be {expected} GS/s.')


def status(ol):
    check(ol)
    word = ol.pdh_control.read(8)
    return dict(sum_enabled=bool(word&1), reference_enabled=bool(word&2),
                commit_ack=bool(word&4), invalid_amplitudes=bool(word&8),
                sum_stalled=bool(word&16), reference_stalled=bool(word&32),
                clipped=bool(word&64), reset_released=bool(word&128),
                fault=bool(word&0x78), carrier_ramping=bool(word&256),
                modulation_ramping=bool(word&512), **frequencies(ol))


def _commit(ol, sum_enabled, reference_enabled, *, clear_faults=False):
    control = (ol.pdh_control.read(0) & 0xc) ^ 4
    if clear_faults:
        control ^= 8
    control |= int(bool(sum_enabled)) | (int(bool(reference_enabled)) << 1)
    ol.pdh_control.write(0, control)
    deadline = time.monotonic()+0.1
    while (ol.pdh_control.read(8) & 4) != (control & 4):
        if time.monotonic() > deadline:
            raise TimeoutError('PDH coefficient commit not acknowledged; check the fabric clock/reset.')
        time.sleep(.001)
    return status(ol)


def stop(ol):
    """Mute both PDH outputs; leave oscillators running and feedback PLLs alone."""
    check(ol)
    return _commit(ol, False, False)


def _coefficients(carrier_amplitude, sideband_amplitude, reference_amplitude, reference_phase_deg):
    if sideband_amplitude is None:
        sideband_amplitude = DEFAULT_SIDEBAND_RATIO * carrier_amplitude
    values = (carrier_amplitude, sideband_amplitude, reference_amplitude, reference_phase_deg)
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Amplitudes and phase must be finite.')
    if any(not 0 <= value <= 1 for value in values[:3]) or carrier_amplitude+sideband_amplitude > 1:
        raise ValueError('Use amplitudes in [0,1], with carrier + 60 MHz amplitude <= 1 for DAC headroom.')
    carrier = round(carrier_amplitude*32767)
    sideband = round(sideband_amplitude*32767)
    if carrier+sideband > 32767:
        raise ValueError('Rounded summed amplitude exceeds signed DAC headroom.')
    reference = round(reference_amplitude*32767)
    phase = round((reference_phase_deg % 360) / 360 * 65536) & 65535
    return carrier, sideband, reference, phase



def _rfdc(ol):
    """Check driver binding before changing either PDH output."""
    import xrfdc
    rf = ol.usp_rf_data_converter_0
    if not hasattr(rf, 'dac_tiles'):
        ip_type = ol.ip_dict['usp_rf_data_converter_0'].get('type', 'unknown')
        raise RuntimeError(
            f'RFDC is bound to {type(rf).__name__}, not xrfdc.RFdc (HWH IP: {ip_type}). '
            'Import xrfdc BEFORE creating ol. For the already running matching image, '
            'reattach with ol = Overlay(ol.bitfile_name, download=False); do not reload '
            'the bitstream or restart clocks. If still unbound, compare the HWH IP type '
            'with xrfdc.RFdc.bindto.')
    return rf


def _check_mixers(ol):
    import xrfdc
    rf = _rfdc(ol)
    problems = []
    for name, block in (('DAC230/0', rf.dac_tiles[2].blocks[0]),
                        ('DAC228/2', rf.dac_tiles[0].blocks[2])):
        settings = dict(block.MixerSettings)
        # Fine-mixer scale and frequency are irrelevant when coarse bypass is
        # selected. Do not test the driver's shared AUTO-scale software flag.
        if (settings['MixerType'] != xrfdc.MIXER_TYPE_COARSE or
                settings['MixerMode'] != xrfdc.MIXER_MODE_R2R or
                settings['CoarseMixFreq'] != xrfdc.COARSE_MIX_BYPASS):
            problems.append(f'{name} must use coarse R2R bypass; readback={settings}')
        if block.InterpolationFactor != 2:
            problems.append(f'{name} interpolation must be 2; readback={block.InterpolationFactor}')
    if problems:
        raise ValueError('PDH converter check: '+ '; '.join(problems))


def set_levels(ol, *, carrier_amplitude=0.55, sideband_amplitude=None, reference_amplitude=0.10,
               reference_phase_deg=0.0, sum_enabled=True, reference_enabled=True):
    """Atomically update amplitudes/reference phase without resetting any NCO.

    Positive phase advances the reference cosine. The physical phase includes
    DAC/filter/cable delays and needs calibration after a converter restart.
    Changes are immediate coefficient steps, not an amplitude/phase ramp.
    Omitting sideband_amplitude uses 0.587654 times the carrier amplitude;
    explicitly pass zero to measure the carrier alone.
    """
    check(ol)
    carrier, sideband, ref, phase = _coefficients(carrier_amplitude, sideband_amplitude,
                                             reference_amplitude, reference_phase_deg)
    _check_mixers(ol)
    if status(ol)['fault']:
        raise RuntimeError('PDH has a sticky fault; inspect status() and rerun configure() to rearm.')
    ol.pdh_amplitudes.write(0, carrier | (sideband << 16))
    ol.pdh_amplitudes.write(8, ref | (phase << 16))
    state = _commit(ol, sum_enabled, reference_enabled)
    if state['fault']:
        raise RuntimeError(f'PDH output muted by hardware: {state}')
    return dict(**frequencies(ol),
                carrier_amplitude=carrier/32767, sideband_amplitude=sideband/32767,
                reference_amplitude=ref/32767,
                reference_phase_deg=phase*360/65536, status=state)


def configure(ol, *, carrier_amplitude=0.0, sideband_amplitude=None,
              reference_amplitude=0.0, reference_phase_deg=0.0):
    """Mute, configure DAC230/0 and DAC228/2, then apply requested levels.

    Import xrfdc before creating ol; run the usual reference-clock startup first.
    Starts tile230 only if it is not ready; never resets/restarts existing tiles.
    Recalibrate physical reference phase after a converter/bitstream restart.
    """
    check(ol)
    _coefficients(carrier_amplitude, sideband_amplitude, reference_amplitude, reference_phase_deg)
    import xrfdc
    rf = _rfdc(ol)
    stop(ol)
    # Normal board initialization already starts tiles228/229. This formerly
    # unused tile uses the refclk distributed by tile229, which must be running.
    if rf.IPStatus['DACTileStatus'][2]['TileState'] != 15:
        rf.dac_tiles[2].StartUp()
    if rf.IPStatus['DACTileStatus'][2]['TileState'] != 15:
        raise RuntimeError('DAC230 did not start. Check the 491.52 MHz reference and tile229 clock distribution.')
    for block in (rf.dac_tiles[2].blocks[0], rf.dac_tiles[0].blocks[2]):
        settings = dict(block.MixerSettings)
        settings.update(Freq=0.0, PhaseOffset=0.0, EventSource=xrfdc.EVNT_SRC_IMMEDIATE,
                        MixerType=xrfdc.MIXER_TYPE_COARSE, MixerMode=xrfdc.MIXER_MODE_R2R,
                        CoarseMixFreq=xrfdc.COARSE_MIX_BYPASS,
                        FineMixerScale=xrfdc.MIXER_SCALE_1P0)
        block.MixerSettings = settings
        block.UpdateEvent(xrfdc.EVENT_MIXER)
        block.NyquistZone = 1
    _check_mixers(ol)
    _commit(ol, False, False, clear_faults=True)
    return set_levels(ol, carrier_amplitude=carrier_amplitude, sideband_amplitude=sideband_amplitude,
                      reference_amplitude=reference_amplitude, reference_phase_deg=reference_phase_deg)


def set_reference_phase(ol, phase_deg):
    """Rotate just the 60 MHz reference; retain all amplitudes and enable bits."""
    check(ol)
    a, r = ol.pdh_amplitudes.read(0), ol.pdh_amplitudes.read(8)
    state = status(ol)
    return set_levels(ol, carrier_amplitude=(a&65535)/32767, sideband_amplitude=(a>>16)/32767,
                      reference_amplitude=(r&65535)/32767,
                      reference_phase_deg=phase_deg, sum_enabled=state['sum_enabled'],
                      reference_enabled=state['reference_enabled'])


def frequency_word(frequency_hz):
    """48-bit FCW; units are turns per 3.44064-GS/s sample for BOTH tones."""
    if not math.isfinite(frequency_hz) or not 0 <= frequency_hz < DDS_SAMPLE_RATE_HZ/2:
        raise ValueError('Frequency must be finite, nonnegative and below 1.72032 GHz.')
    return round(frequency_hz / DDS_SAMPLE_RATE_HZ * 2**48)


def frequencies(ol):
    """Read TARGET frequencies, not the instantaneous frequency during a ramp."""
    c = ol.pdh_carrier_frequency.read(0) | ((ol.pdh_carrier_frequency.read(8)&65535)<<32)
    m = ol.pdh_modulation_frequency.read(0) | ((ol.pdh_modulation_frequency.read(8)&65535)<<32)
    return dict(carrier_target_fcw=c, modulation_target_fcw=m,
                carrier_target_hz=c*DDS_SAMPLE_RATE_HZ/2**48,
                modulation_target_hz=m*DDS_SAMPLE_RATE_HZ/2**48)


def set_fcw(ol, *, carrier_fcw=None, modulation_fcw=None, wait=False):
    """Commit 48-bit targets. Slew is 1024 FCW counts/clock, about 3.077 MHz/s.

    Phase is never reset, including when muted. Reset defaults are 1.2 GHz and
    60 MHz. Updating either target during a ramp immediately redirects that ramp.
    Python commands provide at least 1-Hz resolution; FCW LSB is 12.224 microHz.
    """
    check(ol)
    _check_mixers(ol)
    commands = ((ol.pdh_carrier_frequency, carrier_fcw, .8e9, 1.3e9),
                (ol.pdh_modulation_frequency, modulation_fcw, 1., 100e6))
    for gpio, word, low_hz, high_hz in commands:
        if word is not None:
            if isinstance(word, bool) or int(word) != word or not 0 <= word < 2**48:
                raise ValueError('FCW must be an unsigned 48-bit integer.')
            if not frequency_word(low_hz) <= word <= frequency_word(high_hz):
                raise ValueError(f'Requested frequency is outside {low_hz:g}..{high_hz:g} Hz.')
    state = status(ol)
    if state['fault']:
        raise RuntimeError(f'PDH fault: {state}')
    for gpio, word, _, _ in commands:
        if word is not None:
            gpio.write(0, int(word)&0xffffffff)
            gpio.write(8, int(word)>>32)
    _commit(ol, state['sum_enabled'], state['reference_enabled'])
    if wait:
        wait_frequency(ol)
    return status(ol)


def set_frequency(ol, *, carrier_hz=None, modulation_hz=None, wait=False):
    """Hz convenience wrapper for set_fcw(); does not change amplitude or phase."""
    return set_fcw(ol, carrier_fcw=None if carrier_hz is None else frequency_word(carrier_hz),
                   modulation_fcw=None if modulation_hz is None else frequency_word(modulation_hz), wait=wait)


def wait_frequency(ol, timeout_s=600):
    """Wait for both slews to settle. Interrupting this wait leaves the ramp running."""
    deadline=time.monotonic()+timeout_s
    while True:
        state=status(ol)
        if state['fault']:
            raise RuntimeError(f'PDH fault: {state}')
        if not state['carrier_ramping'] and not state['modulation_ramping']:
            return state
        if time.monotonic()>deadline:
            raise TimeoutError('PDH frequency ramp is still running; inspect status().')
        time.sleep(.05)
