"""PYNQ controls for ADC 224/3 -> DAC 229/1. Frequencies are in Hz.

The FPGA supplies an error to an external analog controller. Load the rebuilt,
matching .bit/.hwh pair before using these functions. Only one GPIO writer.
"""
import math
import time

ADC_SAMPLE_RATE_HZ = 1_966_080_000.0
ERROR_SAMPLE_RATE_HZ = ADC_SAMPLE_RATE_HZ / 8
PHASE_CODES_PER_TURN = 1 << 18


def _signed(value, bits):
    value = int(value) & ((1 << bits) - 1)
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def set_reference_frequency(overlay, frequency_hz, *, restart_phase=False):
    """Commit a 48-bit DDS word, preserving accumulated phase by default.

    Low word is staged first. Toggling bit 16 of the high word commits both
    words on one RF clock edge. Updates are atomic and phase-continuous, but
    software timed; deterministic ramps need a hardware trajectory source here.
    """
    frequency_hz = float(frequency_hz)
    if not math.isfinite(frequency_hz) or not 0 < frequency_hz < ADC_SAMPLE_RATE_HZ / 2:
        raise ValueError("Reference must be finite and between 0 and 983.04 MHz.")
    if restart_phase and overlay.pll_control.read(0x00) & 1:
        raise ValueError("Disable the error output before restarting reference phase.")
    word = round(frequency_hz / ADC_SAMPLE_RATE_HZ * (1 << 48))
    gpio = overlay.pll_frequency
    toggle = ((gpio.read(0x08) >> 16) ^ 1) & 1
    gpio.write(0x00, word & 0xFFFFFFFF)
    gpio.write(0x08, (word >> 32) | (toggle << 16) | (int(restart_phase) << 17))
    deadline = time.monotonic() + 0.1
    while ((overlay.pll_status.read(0x00) >> 22) & 1) != toggle:
        if time.monotonic() > deadline:
            raise TimeoutError("PLL frequency commit was not acknowledged; check RF clock/reset.")
    return word * ADC_SAMPLE_RATE_HZ / (1 << 48)


def configure(overlay, *, reference_frequency_hz=800e6, phase_offset_rad=0.0,
              phase_gain_shift=0, capture_gain_shift=6, minimum_amplitude=64,
              invert=False):
    """Configure while muted; then call enable() to drive the analog controller.

    e = wrap(phase_offset - measured_phase); d = wrap(previous_phase - phase).
    DAC code = saturate((e + capture * 2**capture_gain_shift * d)
                        * 2**phase_gain_shift / 4), with optional sign inversion.
    minimum_amplitude is max(|I|,|Q|) in post-mixer ADC counts (input peak/2).
    One phase radian gives 32768/pi DAC codes at phase_gain_shift=0.
    """
    for name, value, maximum in (("phase_gain_shift", phase_gain_shift, 15),
                                  ("capture_gain_shift", capture_gain_shift, 15),
                                  ("minimum_amplitude", minimum_amplitude, 32767)):
        if not isinstance(value, int) or not 0 <= value <= maximum:
            raise ValueError(f"{name} must be an integer in [0, {maximum}].")
    if not math.isfinite(phase_offset_rad):
        raise ValueError("phase_offset_rad must be finite.")
    p = overlay.ip_dict['usp_rf_data_converter_0']['parameters']
    expected = {'ADC_Data_Type03': 0, 'ADC_Decimation_Mode03': 1,
                'ADC_Data_Width03': 8, 'ADC_Mixer_Type03': 1,
                'DAC_Data_Width11': 14, 'DAC_Interpolation_Mode11': 4}
    for name, value in expected.items():
        if int(p[name]) != value:
            raise ValueError(f"Incompatible RFDC configuration: {name} must equal {value}.")
    if not math.isclose(float(p['ADC0_Sampling_Rate']) * 1e9, ADC_SAMPLE_RATE_HZ):
        raise ValueError("ADC tile 224 must run at 1.96608 GS/s.")
    overlay.pll_control.write(0x00, 0)
    import xrfdc
    dac = overlay.usp_rf_data_converter_0.dac_tiles[1].blocks[1]
    settings = dict(dac.MixerSettings)
    settings.update(Freq=0.0, PhaseOffset=0.0, EventSource=xrfdc.EVNT_SRC_IMMEDIATE,
                    MixerType=xrfdc.MIXER_TYPE_FINE, MixerMode=xrfdc.MIXER_MODE_C2R,
                    FineMixerScale=xrfdc.MIXER_SCALE_1P0)
    dac.MixerSettings = settings
    # Setting frequency to zero alone freezes an arbitrary old NCO phase.
    # Restart it so C2R passes +I, rather than I*cos(old_phase).
    dac.ResetNCOPhase()
    dac.UpdateEvent(xrfdc.EVENT_MIXER)
    actual_hz = set_reference_frequency(overlay, reference_frequency_hz, restart_phase=True)
    phase_code = round(phase_offset_rad / (2 * math.pi) * PHASE_CODES_PER_TURN)
    overlay.pll_control.write(0x08, phase_code & 0x3FFFF)
    control = (int(invert) << 2) | (phase_gain_shift << 4) | (capture_gain_shift << 8)
    overlay.pll_control.write(0x00, control | (minimum_amplitude << 16))
    return actual_hz


def enable(overlay, enabled=True):
    value = overlay.pll_control.read(0x00)
    overlay.pll_control.write(0x00, (value & ~1) | int(bool(enabled)))


def enable_capture(overlay, enabled=True):
    """Disable after acquisition to remove the frequency discriminator term."""
    value = overlay.pll_control.read(0x00)
    overlay.pll_control.write(0x00, (value & ~2) | (int(bool(enabled)) << 1))


def set_gains(overlay, *, phase_gain_shift, capture_gain_shift):
    """Set both GPIO gain fields atomically, preserving enable and other flags.

    Each shift is 0..15 (gain 1..32768 in powers of two). Phase gain scales
    the whole error; capture gain is the frequency term relative to phase.
    Live changes take effect within the two-stage error/output pipeline.
    """
    for value in (phase_gain_shift, capture_gain_shift):
        if not isinstance(value, int) or not 0 <= value <= 15:
            raise ValueError("Gain shifts must be integers in [0, 15].")
    value = overlay.pll_control.read(0x00)
    value = (value & ~0xFF0) | (phase_gain_shift << 4) | (capture_gain_shift << 8)
    overlay.pll_control.write(0x00, value)


def status(overlay):
    """Live diagnostics; phase and frequency reads are not simultaneous."""
    value = overlay.pll_status.read(0x00)
    frequency_code = _signed(overlay.pll_status.read(0x08), 18)
    return dict(phase_error_rad=_signed(value, 18) * (2 * math.pi / PHASE_CODES_PER_TURN),
                frequency_error_hz=frequency_code * ERROR_SAMPLE_RATE_HZ / PHASE_CODES_PER_TURN,
                enabled=bool(value & (1 << 18)), valid=bool(value & (1 << 19)),
                saturated=bool(value & (1 << 20)), dac_stall_seen=bool(value & (1 << 21)))
