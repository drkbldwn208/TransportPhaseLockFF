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
              invert=True):
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
    # Refuse an old overlay before touching outputs or the RFDC.
    if overlay.pll_acquisition_status.read(0x08) >> 24 != 0xA3:
        raise ValueError("Load the matching three-stage PLL .bit/.hwh pair.")
    p = overlay.ip_dict['usp_rf_data_converter_0']['parameters']
    expected = {'ADC_Data_Type03': 0, 'ADC_Decimation_Mode03': 1,
                'ADC_Data_Width03': 8, 'ADC_Mixer_Type03': 1, 'ADC_Nyquist03': 0,
                'DAC_Data_Width11': 14, 'DAC_Interpolation_Mode11': 4}
    for name, value in expected.items():
        if int(p[name]) != value:
            raise ValueError(f"Incompatible RFDC configuration: {name} must equal {value}.")
    if not math.isclose(float(p['ADC0_Sampling_Rate']) * 1e9, ADC_SAMPLE_RATE_HZ):
        raise ValueError("ADC tile 224 must run at 1.96608 GS/s.")
    overlay.pll_control.write(0x00, 0)
    configure_acquisition(overlay)
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
    """Toggle the derivative ONLY in legacy mode 0; use select_stage for stages 1..3."""
    if overlay.pll_acquisition.read(0x00) & 7:
        raise ValueError("Capture flag applies only to legacy mode 0; use select_stage().")
    value = overlay.pll_control.read(0x00)
    overlay.pll_control.write(0x00, (value & ~2) | (int(bool(enabled)) << 1))


def set_gains(overlay, *, phase_gain_shift, capture_gain_shift):
    """Set both GPIO gain fields atomically, preserving enable and other flags.

    Each shift is 0..15 (gain 1..32768 in powers of two). Phase gain scales
    the whole error; capture gain is the frequency term relative to phase.
    Live changes pass through the gain, handoff and DAC output registers.
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


def configure_acquisition(overlay, *, stage=1, transition_interval_log2=4,
                          coarse_gain_shift=0, minimum_fft_peak=32):
    """Set acquisition parameters while muted. The reference NCO is untouched.

    stage: 0=legacy wrapped, 1=FFT, 2=phase+frequency, 3=unwrapped phase.
    A handoff offset decays by one DAC code every 2**transition_interval_log2
    fabric clocks. Default 4: at most 4.27 ms for a full-span mode discrepancy.
    Cycle memory is signed 24-bit, saturating only at its numeric limits.
    minimum_fft_peak is FFT magnitude in codes, about raw ADC peak/8 on-bin.
    """
    for name, value, low, high in (
        ('stage',stage,0,3), ('transition_interval_log2',transition_interval_log2,0,15),
        ('coarse_gain_shift',coarse_gain_shift,0,15),
        ('minimum_fft_peak',minimum_fft_peak,1,32767)):
        if not isinstance(value,int) or not low <= value <= high:
            raise ValueError(f"{name} must be an integer in [{low}, {high}].")
    if overlay.pll_control.read(0x00) & 1:
        raise ValueError("Mute the output before changing acquisition parameters.")
    value = stage | (transition_interval_log2<<4) | (coarse_gain_shift<<8)
    value |= minimum_fft_peak<<16
    overlay.pll_acquisition.write(0x08,0)
    overlay.pll_acquisition.write(0x00,value)


def acquisition_status(overlay):
    """Read stage/FFT diagnostics; reads are live, not an atomic snapshot.

    Stage 3 removes the derivative term. 'fine_ready' is an entry qualification,
    NOT a measurement of closed-loop phase lock. A settled handoff is likewise
    only a digital condition. Verify phase lock on the scope before proceeding.
    """
    a = overlay.pll_acquisition_status.read(0x00)
    f = overlay.pll_acquisition_status.read(0x08)
    if f >> 24 != 0xA3:
        raise ValueError("Acquisition register version mismatch.")
    return dict(stage=a&3, dc_test=bool(a&4), transitioning=bool(a&8),
                pending=bool(a&16), near_ready=bool(a&32), fine_ready=bool(a&64),
                output_valid=bool(a&128), remembered_turns=_signed(a>>8,24),
                fft_frequency_hz=(f&1023)*ADC_SAMPLE_RATE_HZ/1024,
                fft_valid=bool(f&(1<<10)), fft_weak=bool(f&(1<<11)),
                fft_overflow_seen=bool(f&(1<<12)), fft_protocol_fault=bool(f&(1<<13)),
                fft_frame=(f>>16)&255)


def select_stage(overlay, stage, *, wait=True, timeout_s=5.0):
    """Request a qualified, continuous handoff without changing NCO phase/gains.

    Stage 2 waits for FFT detuning <80 MHz and valid fine phase. Stage 3 waits
    for FFT detuning <8 MHz and |fine frequency error| <=3 MHz for 16.67 us.
    With wait=False the request remains pending until qualified. With wait=True,
    timeout cancels the request by restoring the previous request (also ramped).
    There is no automatic fallback: inspect diagnostics and select stage 1 to
    reacquire after loss of signal. Analog controller enables remain external.
    """
    if not isinstance(stage,int) or not 0 <= stage <= 3:
        raise ValueError("stage must be 0, 1, 2, or 3.")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be positive and finite.")
    if wait and not overlay.pll_control.read(0x00) & 1:
        raise ValueError("Output is muted; use wait=False to select the startup stage.")
    old = overlay.pll_acquisition.read(0x00)
    overlay.pll_acquisition.write(0x00,(old & ~7) | stage)
    if not wait: return acquisition_status(overlay)
    deadline=time.monotonic()+timeout_s
    while True:
        state=acquisition_status(overlay)
        if state['stage']==stage and not any(state[k] for k in ('dc_test','pending','transitioning')):
            return state
        if time.monotonic()>=deadline:
            overlay.pll_acquisition.write(0x00,old)
            raise TimeoutError(f"Stage {stage} did not qualify/settle; restored previous request. Last state: {state}")
        time.sleep(0.005)


def set_dc_output(overlay, code, *, enabled=True):
    """Select a literal signed 16-bit DC DAC code; global enable() still applies.

    Independent of ADC validity, phase/capture gains and polarity. Entry/exit
    uses the same handoff ramp. Wait for transitioning=False before measuring.
    Changing code while already in DC mode is immediate. RFDC mixer settings
    may translate this DC into a tone; restore a zero-frequency/phase mixer
    before returning to the PLL (configure() does this while muted).
    """
    if not isinstance(code,int) or not -32768 <= code <= 32767:
        raise ValueError("DC code must be an integer in [-32768, 32767].")
    overlay.pll_acquisition.write(0x08,code & 0xffff)
    value=overlay.pll_acquisition.read(0x00)
    overlay.pll_acquisition.write(0x00,(value & ~4) | (int(bool(enabled))<<2))
