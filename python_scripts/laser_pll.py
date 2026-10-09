"""PYNQ controls for ADC 224/3 -> DAC 229/1. Frequencies are in Hz.

The FPGA supplies an error to an external analog controller. Load the rebuilt,
matching .bit/.hwh pair before using these functions. Only one GPIO writer.
"""
import math
import time

ADC_SAMPLE_RATE_HZ = 1_966_080_000.0
ERROR_SAMPLE_RATE_HZ = ADC_SAMPLE_RATE_HZ / 8
PHASE_CODES_PER_TURN = 1 << 18
STAGE3_PHASE_DIVISOR = 160
FPGA_VERSION = 0xA5


def _check_version(overlay):
    actual = overlay.pll_acquisition_status.read(0x08) >> 24
    if actual != FPGA_VERSION:
        raise ValueError(f"Helper requires A5 tracking/IQ firmware; FPGA reports 0x{actual:02x}. "
                         "Load the matching .bit/.hwh/helper package; reload laser_pll after replacing it.")


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
    At phase_gain_shift=0, stages 0/2 give 32768/pi DAC codes/radian.
    Stage 3 divides that slope by 160, with full DAC span across 160 turns.
    """
    for name, value, maximum in (("phase_gain_shift", phase_gain_shift, 15),
                                  ("capture_gain_shift", capture_gain_shift, 15),
                                  ("minimum_amplitude", minimum_amplitude, 32767)):
        if not isinstance(value, int) or not 0 <= value <= maximum:
            raise ValueError(f"{name} must be an integer in [0, {maximum}].")
    if not math.isfinite(phase_offset_rad):
        raise ValueError("phase_offset_rad must be finite.")
    # Refuse an old overlay before touching outputs or the RFDC.
    _check_version(overlay)
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
    overlay.pll_tracking.write(0x00, 14 << 4)
    overlay.pll_monitor.write(0x00, 0)
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
    if overlay.pll_acquisition.read(0x00) & 15:
        raise ValueError("Capture flag applies only to legacy mode 0; use select_stage().")
    value = overlay.pll_control.read(0x00)
    overlay.pll_control.write(0x00, (value & ~2) | (int(bool(enabled)) << 1))


def set_gains(overlay, *, phase_gain_shift, capture_gain_shift):
    """Set both GPIO gain fields atomically, preserving enable and other flags.

    Each shift is 0..15. Stages 0/2 retain their original phase sensitivity.
    Stage 3 slope is 2**phase_gain_shift/160 times that original sensitivity:
    shifts 0/1/2 give +/-80/40/20 turns at the DAC rails. Capture gain is the
    frequency term relative to phase in stages 0/2. Gain writes are immediate,
    not ramped handoffs; change at low error or between acquisition attempts.
    """
    if overlay.pll_acquisition.read(0x00) & 8:
        raise ValueError("Use set_tracking_gain() for smooth sensitivity changes in stage 4.")
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

    Stage 3 removes the derivative term. With the manual-entry FPGA revision,
    'fine_ready' means valid fine-phase data, NOT frequency qualification or lock.
    A settled handoff is likewise only a digital condition. Verify phase lock
    on the scope before proceeding.
    """
    a = overlay.pll_acquisition_status.read(0x00)
    f = overlay.pll_acquisition_status.read(0x08)
    if f >> 24 != FPGA_VERSION:
        raise ValueError("Acquisition register version mismatch.")
    return dict(stage=a&7, dc_test=(a&7)==5, transitioning=bool(a&8),
                pending=bool(a&16), near_ready=bool(a&32), fine_ready=bool(a&64),
                output_valid=bool(a&128), remembered_turns=_signed(a>>8,24),
                fft_frequency_hz=(f&1023)*ADC_SAMPLE_RATE_HZ/1024,
                fft_valid=bool(f&(1<<10)), fft_weak=bool(f&(1<<11)),
                fft_overflow_seen=bool(f&(1<<12)), fft_protocol_fault=bool(f&(1<<13)),
                fft_frame=(f>>16)&255)


def select_stage(overlay, stage, *, wait=True, timeout_s=5.0):
    """Request a qualified, continuous handoff without changing NCO phase/gains.

    Stage 2 waits for FFT detuning <80 MHz and valid fine phase. Stage 3 is
    manual: only valid fine data and five clocks of wrap/scaler preparation
    are required, with no frequency, dwell or FFT gate. This requires the
    A5 tracking/IQ FPGA bitstream; updating this helper alone is insufficient.
    Stage 4 follows a settled stage 3 and saves its current phase/DAC operating
    point. Set its target with set_tracking_gain(); no optical-lock detector is
    implied. Stage-4 gain ramps are separate from the mode handoff's offset ramp.
    Frequency offsets can accumulate remembered turns and rail the DAC.
    With wait=False the request remains pending until qualified. With wait=True,
    timeout cancels the request by restoring the previous request (also ramped).
    There is no automatic fallback: inspect diagnostics and select stage 1 to
    reacquire after loss of signal. Analog controller enables remain external.
    """
    if not isinstance(stage,int) or not 0 <= stage <= 4:
        raise ValueError("stage must be 0, 1, 2, 3, or 4.")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be positive and finite.")
    if wait and not overlay.pll_control.read(0x00) & 1:
        raise ValueError("Output is muted; use wait=False to select the startup stage.")
    old = overlay.pll_acquisition.read(0x00)
    if stage == 4:
        state = acquisition_status(overlay)
        if state['stage'] not in (3, 4) or state['transitioning'] or state['pending']:
            raise ValueError("Enter tracking from settled stage 3 after verifying optical lock.")
        if ((overlay.pll_control.read(0x00) >> 4) & 15) > 8:
            raise ValueError("Stage-4 entry supports initial phase gain shifts 0..8.")
    overlay.pll_acquisition.write(0x00,(old & ~15) | (8 if stage == 4 else stage))
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


def tracking_status(overlay):
    """Actual sensitivity relative to stage-3 shift 0; all quantities are live."""
    _check_version(overlay)
    value = overlay.pll_tracking.read(0x08)
    return dict(initialized=bool(value & (1 << 31)), ramping=bool(value & (1 << 30)),
                saturated=bool(value & (1 << 29)), valid=bool(value & (1 << 28)),
                gain_relative_to_stage3=(value & 0x3ffffff) / 104858.0,
                target_shift=overlay.pll_tracking.read(0x00) & 15)


def set_tracking_gain(overlay, shift, *, ramp_interval_log2=14, wait=True, timeout_s=5.0):
    """Stage 4: slew toward 2**shift times the stage-3 shift-0 sensitivity.

    shift 0..8; each update is <=1/256 of current gain. Default interval 14
    gives about 12 ms per doubling, 95 ms for 1x -> 256x. Phase fluctuations
    still pass at full rate; only gain changes slowly. The saved phase and DAC
    bias persist across updates. Increasing sensitivity raises analog loop gain
    too: test one doubling at a time, or reduce controller gain correspondingly.
    In stage 3, use wait=False to prepare the target before select_stage(ol,4).
    A timeout leaves the requested ramp active; it does not reset the lock.
    """
    for name, value, maximum in (("shift",shift,8), ("ramp_interval_log2",ramp_interval_log2,20)):
        if not isinstance(value,int) or not 0 <= value <= maximum:
            raise ValueError(f"{name} must be an integer in [0, {maximum}].")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be positive and finite.")
    _check_version(overlay)
    if wait and acquisition_status(overlay)['stage'] != 4:
        raise ValueError("Use wait=False to prepare tracking gain before entering stage 4.")
    overlay.pll_tracking.write(0x00, shift | (ramp_interval_log2 << 4))
    if not wait:
        return tracking_status(overlay)
    target = 104858 << shift
    deadline = time.monotonic() + timeout_s
    while True:
        value = overlay.pll_tracking.read(0x08)
        if value & (1 << 28) and not value & (1 << 30) and (value & 0x3ffffff) == target:
            return tracking_status(overlay)
        if time.monotonic() >= deadline:
            raise TimeoutError("Tracking gain has not settled; requested ramp remains active.")
        time.sleep(0.001)


def capture_iq(overlay, samples=65536, *, decimation_log2=4, timeout_s=None):
    """Capture post-DDC I/Q before CORDIC/gains; never changes the laser controls.

    Returns dict(i_adc_counts, q_adc_counts, sample_rate_hz, decimation_log2).
    Each output is a signed boxcar mean over 2**decimation_log2 fabric samples,
    retaining 8 fractional ADC bits. Default rate 15.36 MS/s, 246 MB/s to DMA.
    Boxcar filtering has limited alias rejection: repeat PSDs at different rates.
    At zero decimation DMA needs 3.93 GB/s; long captures may overflow. Any lost
    or invalid samples raise an error rather than silently distorting a PSD.
    Separate captures have gaps; do not concatenate them as one uniform record.
    """
    for name, value, low, high in (("samples",samples,1,1048575),
                                   ("decimation_log2",decimation_log2,0,16)):
        if not isinstance(value,int) or not low <= value <= high:
            raise ValueError(f"{name} must be an integer in [{low}, {high}].")
    sample_rate_hz = ERROR_SAMPLE_RATE_HZ / (1 << decimation_log2)
    if timeout_s is None:
        timeout_s = samples / sample_rate_hz + 2.0
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be positive and finite.")
    _check_version(overlay)
    if not overlay.pll_control.read(0x00) & 1:
        raise ValueError("Enable the PLL detector before taking I/Q data.")
    import numpy as np
    from pynq import allocate
    monitor = overlay.pll_monitor
    dma = overlay.axi_dma_3
    if monitor.read(0x00) & 1:
        raise RuntimeError("An I/Q capture is already armed.")
    # Arm DMA first. Raising monitor enable releases/empties only its own FIFO.
    buffer = allocate(shape=(samples,2), dtype=np.int64)
    transfer_started = False
    try:
        dma.recvchannel.transfer(buffer)
        transfer_started = True
        monitor.write(0x00, (samples << 12) | (decimation_log2 << 1) | 1)
        deadline = time.monotonic() + timeout_s
        while not dma.recvchannel.idle:
            if dma.mmio.read(0x34) & 0x70:
                raise RuntimeError("I/Q DMA reported a transfer error.")
            if time.monotonic() >= deadline:
                raise TimeoutError("I/Q DMA capture timed out.")
            time.sleep(0.001)
        dma.recvchannel.wait()  # complete driver bookkeeping and invalidate cache
        transfer_started = False
        status_word = monitor.read(0x08)
        if status_word & 0xc or not status_word & 2 or status_word >> 12 != samples:
            raise RuntimeError(f"I/Q record has lost/invalid samples or wrong length (status 0x{status_word:08x}); "
                               "increase decimation if overflow bit 2 is set.")
        return dict(i_adc_counts=np.array(buffer[:,1],dtype=float)/256.0,
                    q_adc_counts=np.array(buffer[:,0],dtype=float)/256.0,
                    sample_rate_hz=sample_rate_hz, decimation_log2=decimation_log2)
    finally:
        monitor.write(0x00, 0)
        if transfer_started:
            # Stop this S2MM receiver before freeing memory still owned by DMA.
            # The PLL and the other DMA engines are unaffected.
            dma.recvchannel.stop()
            dma.recvchannel.start()
        buffer.freebuffer()


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
