"""Pure coefficient calculation for the RTL outline; performs no board writes."""
import math

CLOCK_HZ = 245_760_000
SAMPLE_HZ = 14 * CLOCK_HZ
PHASE_MODULUS = 1 << 48
SIDEBAND_RATIO = 1.081979112658792 / 1.8411848682178047


def configuration_words(carrier_hz=1.2e9, carrier_amplitude=.55,
                        sideband_amplitude=None, reference_amplitude=.1,
                        reference_phase_deg=0, sum_enabled=True, reference_enabled=True):
    """Return 76 logical words plus actual Hz; word 3 is reserved.

    Write words 0,1,2,4..75 to the inactive bank, pulse cfg_commit, then wait
    for cfg_busy=0 before starting another update. Frequency and all coefficients
    form ONE transaction. This is not yet an AXI address map or PYNQ driver.
    """
    if sideband_amplitude is None:
        sideband_amplitude = carrier_amplitude * SIDEBAND_RATIO
    values = (carrier_hz, carrier_amplitude, sideband_amplitude,
              reference_amplitude, reference_phase_deg)
    if not all(math.isfinite(x) for x in values):
        raise ValueError('Frequency, amplitudes and phase must be finite.')
    if not 800e6 <= carrier_hz <= 1.3e9:
        raise ValueError('Carrier must be between 0.8 and 1.3 GHz.')
    if any(not 0 <= a <= 1 for a in values[1:4]) or carrier_amplitude+sideband_amplitude > 1:
        raise ValueError('Amplitudes must be 0..1, with carrier + sideband <= 1.')
    ac, am, ar = (round(a*32767) for a in values[1:4])
    if ac+am > 32767:
        raise ValueError('Rounded sum exceeds DAC headroom.')
    fcw = round(carrier_hz / SAMPLE_HZ * PHASE_MODULUS)
    frame_increment = (14 * fcw) % PHASE_MODULUS
    words = [frame_increment & 0xffffffff, frame_increment >> 32,
             int(bool(sum_enabled)) | (int(bool(reference_enabled)) << 1), 0]
    # Coefficients are A*cos(delta), -A*sin(delta); the minus sign makes a
    # positive phase offset advance the waveform. Reference is 8 samples/word.
    for lanes, amplitude, step, offset in (
        (14, ac, 2*math.pi*fcw/PHASE_MODULUS, 0),
        (14, am, 2*math.pi*60e6/SAMPLE_HZ, 0),
        (8, ar, 2*math.pi*60e6/(8*CLOCK_HZ), math.radians(reference_phase_deg % 360)),
    ):
        for k in range(lanes):
            angle = offset + k*step
            for value in (4*amplitude*math.cos(angle), -4*amplitude*math.sin(angle)):
                words.append(round(value) & 0x3ffff)
    assert len(words) == 76
    return words, fcw*SAMPLE_HZ/PHASE_MODULUS
