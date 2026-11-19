"""Summed 1.2 GHz + 60 MHz EOM drive and coherent, phase-adjustable 60 MHz LO.

DAC229/2 (tile 1 block 2): seven complex samples/clock, RFDC mixer +630 MHz.
DAC228/2 (tile 0 block 2): eight real samples/clock, RFDC mixer bypass.
Amplitudes are fractions of signed digital full scale, NOT calibrated volts.
These fixed frequencies assume the existing common 245.76 MHz fabric clock.
"""
import math
import time

FEATURE_VERSION = 0x50444801
RF_MIXER_HZ = 630e6
CARRIER_HZ = 1.2e9
MODULATION_HZ = 60e6
# beta_PDH / beta_offset at their ideal PDH-slope maxima; assumes equal Vpi
# and RF voltage transfer at 60 MHz and 1.2 GHz. Calibrate on the optical setup.
DEFAULT_SIDEBAND_RATIO = 1.081979112658792 / 1.8411848682178047


def check(ol):
    if not hasattr(ol, 'pdh_version') or ol.pdh_version.read(0) != FEATURE_VERSION:
        raise ValueError('Load the matching PDH bitstream/HWH and pdh_tones.py helper.')
    parameters = ol.ip_dict['usp_rf_data_converter_0']['parameters']
    for name, expected in {'DAC_Data_Width12':14, 'DAC_Interpolation_Mode12':4,
                           'DAC_Data_Width02':8, 'DAC_Interpolation_Mode02':2}.items():
        if int(parameters[name]) != expected:
            raise ValueError(f'{name} must be {expected} for this waveform generator.')
    for name, expected in {'DAC0_Sampling_Rate':3.93216, 'DAC1_Sampling_Rate':6.88128}.items():
        if abs(float(parameters[name])-expected) > 1e-9:
            raise ValueError(f'{name} must be {expected} GS/s.')


def status(ol):
    check(ol)
    word = ol.pdh_control.read(8)
    return dict(sum_enabled=bool(word&1), reference_enabled=bool(word&2),
                commit_ack=bool(word&4), invalid_amplitudes=bool(word&8),
                sum_stalled=bool(word&16), reference_stalled=bool(word&32),
                clipped=bool(word&64), reset_released=bool(word&128),
                fault=bool(word&0x78))


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
    angle = math.radians(reference_phase_deg % 360)
    # r(t)=A*cos(omega*t+phase) = A*cos(phase)*cos(omega*t) - A*sin(phase)*sin(omega*t).
    ref_cos = round(reference_amplitude*32767*math.cos(angle))
    ref_sin = round(-reference_amplitude*32767*math.sin(angle))
    return carrier, sideband, ref_cos, ref_sin


def _check_mixers(ol):
    import xrfdc
    rf = ol.usp_rf_data_converter_0
    source = rf.dac_tiles[1].blocks[2]
    reference = rf.dac_tiles[0].blocks[2]
    a, b = source.MixerSettings, reference.MixerSettings
    if (abs(a['Freq']-630.0)>1e-6 or a['MixerType'] != xrfdc.MIXER_TYPE_FINE or
            a['MixerMode'] != xrfdc.MIXER_MODE_C2R or a['FineMixerScale'] != xrfdc.MIXER_SCALE_1P0 or
            b['MixerType'] != xrfdc.MIXER_TYPE_COARSE or b['MixerMode'] != xrfdc.MIXER_MODE_R2R or
            b['CoarseMixFreq'] != xrfdc.COARSE_MIX_BYPASS):
        raise ValueError('PDH RFDC settings changed; call configure() with outputs muted first.')
    if source.InterpolationFactor != 4 or reference.InterpolationFactor != 2:
        raise ValueError('PDH DAC interpolation factors must remain 4 and 2.')


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
    carrier, sideband, rc, rs = _coefficients(carrier_amplitude, sideband_amplitude,
                                             reference_amplitude, reference_phase_deg)
    _check_mixers(ol)
    if status(ol)['fault']:
        raise RuntimeError('PDH has a sticky fault; inspect status() and rerun configure() to rearm.')
    ol.pdh_amplitudes.write(0, carrier | (sideband << 16))
    ol.pdh_amplitudes.write(8, (rc & 65535) | ((rs & 65535) << 16))
    state = _commit(ol, sum_enabled, reference_enabled)
    if state['fault']:
        raise RuntimeError(f'PDH output muted by hardware: {state}')
    return dict(carrier_hz=CARRIER_HZ, sideband_hz=MODULATION_HZ,
                carrier_amplitude=carrier/32767, sideband_amplitude=sideband/32767,
                reference_amplitude=math.hypot(rc,rs)/32767,
                reference_phase_deg=math.degrees(math.atan2(-rs,rc)), status=state)


def configure(ol, *, carrier_amplitude=0.0, sideband_amplitude=None,
              reference_amplitude=0.0, reference_phase_deg=0.0):
    """Mute, configure ONLY DAC229/2 and DAC228/2, then apply requested levels.

    Run the usual RFSoC clock and tile startup first. This does not download a
    bitstream or initialize/restart other channels. Resetting the source NCO
    changes the absolute analog reference phase; calibrate after this call.
    """
    check(ol)
    _coefficients(carrier_amplitude, sideband_amplitude, reference_amplitude, reference_phase_deg)
    import xrfdc
    stop(ol)
    rf = ol.usp_rf_data_converter_0
    source = rf.dac_tiles[1].blocks[2]
    reference = rf.dac_tiles[0].blocks[2]
    source_config = dict(source.MixerSettings)
    source_config.update(Freq=630.0, PhaseOffset=0.0, EventSource=xrfdc.EVNT_SRC_IMMEDIATE,
                         MixerType=xrfdc.MIXER_TYPE_FINE, MixerMode=xrfdc.MIXER_MODE_C2R,
                         CoarseMixFreq=xrfdc.COARSE_MIX_BYPASS, FineMixerScale=xrfdc.MIXER_SCALE_1P0)
    reference_config = dict(reference.MixerSettings)
    reference_config.update(Freq=0.0, PhaseOffset=0.0, EventSource=xrfdc.EVNT_SRC_IMMEDIATE,
                            MixerType=xrfdc.MIXER_TYPE_COARSE, MixerMode=xrfdc.MIXER_MODE_R2R,
                            CoarseMixFreq=xrfdc.COARSE_MIX_BYPASS)
    source.MixerSettings = source_config
    source.ResetNCOPhase()
    source.UpdateEvent(xrfdc.EVENT_MIXER)
    reference.MixerSettings = reference_config
    reference.UpdateEvent(xrfdc.EVENT_MIXER)
    source.NyquistZone = 1
    reference.NyquistZone = 1
    _check_mixers(ol)
    _commit(ol, False, False, clear_faults=True)
    return set_levels(ol, carrier_amplitude=carrier_amplitude, sideband_amplitude=sideband_amplitude,
                      reference_amplitude=reference_amplitude, reference_phase_deg=reference_phase_deg)


def set_reference_phase(ol, phase_deg):
    """Rotate just the 60 MHz reference; retain all amplitudes and enable bits."""
    check(ol)
    a, r = ol.pdh_amplitudes.read(0), ol.pdh_amplitudes.read(8)
    signed = lambda word: word-65536 if word&32768 else word
    rc, rs = signed(r&65535), signed(r>>16)
    state = status(ol)
    return set_levels(ol, carrier_amplitude=(a&65535)/32767, sideband_amplitude=(a>>16)/32767,
                      reference_amplitude=min(1.0, math.hypot(rc,rs)/32767),
                      reference_phase_deg=phase_deg, sum_enabled=state['sum_enabled'],
                      reference_enabled=state['reference_enabled'])
