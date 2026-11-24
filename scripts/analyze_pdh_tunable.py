"""Numerical design study of shared DDS + parallel rotations for the PDH DAC.

This does not edit/open the Vivado project or model analog DAC imperfections.
The CORDIC is an explicit integer reference algorithm, NOT AMD's bit-accurate
IP model. Results support architecture selection, not bitstream verification.
Frequencies are snapped to FFT bins (reported), avoiding carrier leakage.
"""
from pathlib import Path
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pdh_matplotlib")
import numpy as np
from scipy.fft import rfft, rfftfreq
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/pdh_tunable_analysis"
CLOCK_HZ = 245_760_000
LANES = 14
SAMPLE_HZ = LANES * CLOCK_HZ
PHASE_BITS = 48
PHASE_MODULUS = 1 << PHASE_BITS
PHASE_MASK = PHASE_MODULUS - 1
SIDEBAND_RATIO = 1.081979112658792 / 1.8411848682178047


def cordic(phase, iterations=24, input_phase_bits=24):
    """Return cos/sin as signed Q22 integers, with 32-bit angle/Q28 internals.

    Round the input angle to input_phase_bits over one turn. Coarse rotation
    handles all four quadrants. The micro-rotations use arithmetic shifts;
    scale compensation is in the starting vector. No recursive oscillator.
    """
    discard = PHASE_BITS - input_phase_bits
    phase = ((phase + (1 << (discard - 1))) & PHASE_MASK) >> discard
    angle = phase.astype(np.int64) << (32 - input_phase_bits)
    angle = np.where(angle >= (1 << 31), angle - (1 << 32), angle)
    flip = (angle > (1 << 30)) | (angle < -(1 << 30))
    angle = np.where(angle > (1 << 30), angle - (1 << 31), angle)
    angle = np.where(angle < -(1 << 30), angle + (1 << 31), angle)
    steps = np.arange(iterations)
    gain = np.prod(np.sqrt(1.0 + 2.0 ** (-2 * steps)))
    angles = np.rint(np.arctan(2.0 ** -steps) / (2 * np.pi) * (1 << 32)).astype(np.int64)
    x = np.full(len(phase), round((1 << 28) / gain), dtype=np.int64)
    y = np.zeros_like(x)
    for shift, delta in enumerate(angles):
        direction = np.where(angle >= 0, 1, -1)
        x, y = x - direction * (y >> shift), y + direction * (x >> shift)
        angle -= direction * delta
    x, y = np.where(flip, -x, x), np.where(flip, -y, y)
    return (x + 32) >> 6, (y + 32) >> 6, 22


def sine_interpolated(phase):
    """512 quarter-wave intervals, 18-bit endpoints, 10 fractional bits.

    Store each base and positive slope together (18 + 9 bits). Each sine/cosine
    pair uses two ports on one BRAM36. Midpoint sampling preserves symmetry.
    """
    table = np.rint(131071 * np.sin(np.arange(513) * np.pi / 1024)).astype(np.int64)
    p = phase.astype(np.int64)
    address = (p >> 27) & ((1 << 19) - 1)
    address = np.where((p >> 46) & 1, address ^ ((1 << 19) - 1), address)
    index = address >> 10
    fraction = 2 * (address & 1023) + 1
    magnitude = table[index] + ((np.diff(table)[index] * fraction + 1024) >> 11)
    return np.where((p >> 47) & 1, -magnitude, magnitude)


def sine_pair(phase, method):
    if method == "interpolated":
        return (sine_interpolated((phase + (1 << 46)) & PHASE_MASK),
                sine_interpolated(phase), 17)
    if method == "cordic24":
        return cordic(phase)
    if method == "cordic18":
        return cordic(phase, iterations=18, input_phase_bits=18)
    raise ValueError(method)


def samples(frequency_hz, frames, method, sideband=True):
    """Integer waveform with 18-bit, amplitude-weighted rotation coefficients.

    Each sample uses two multiplications per tone. Coefficients have units of
    DAC counts * 4. This fits an 18-bit signed DSP input even at full amplitude.
    The sine generator's output fits the other DSP input (up to 24 bits here).
    Sum both tones before the sole final rounding to 16-bit DAC input codes.
    """
    fcw = round(frequency_hz / SAMPLE_HZ * PHASE_MODULUS)
    actual_hz = fcw * SAMPLE_HZ / PHASE_MODULUS
    n = np.arange(frames, dtype=np.uint64)
    carrier_phase = (n * np.uint64(LANES * fcw)) & np.uint64(PHASE_MASK)
    mod_phase = ((n * 125) & 511) << 39  # Exactly 60 MHz at this fabric clock.
    c, s, frac = sine_pair(carrier_phase, method)
    cm, sm, mod_frac = sine_pair(mod_phase, method)
    assert frac == mod_frac
    ac = round(0.55 * 32767)
    am = round(0.55 * SIDEBAND_RATIO * 32767) if sideband else 0
    output = np.empty((frames, LANES), dtype=np.int16)
    phase_step = 2 * np.pi * fcw / PHASE_MODULUS
    for lane in range(LANES):
        angle = lane * phase_step
        angle_mod = lane * 2 * np.pi * 60e6 / SAMPLE_HZ
        cc, cs = round(4 * ac * np.cos(angle)), round(-4 * ac * np.sin(angle))
        mc, ms = round(4 * am * np.cos(angle_mod)), round(-4 * am * np.sin(angle_mod))
        product = c * cc + s * cs + cm * mc + sm * ms
        codes = (product + (1 << (frac + 1))) >> (frac + 2)
        assert codes.min() >= -32768 and codes.max() <= 32767
        output[:, lane] = codes
    return output.ravel(), actual_hz


def spectrum(frequency_hz, frames, method, sideband=True):
    bin_hz = CLOCK_HZ / frames
    coherent_hz = round(frequency_hz / bin_hz) * bin_hz
    data, actual_hz = samples(coherent_hz, frames, method, sideband)
    amplitude = 2 * abs(rfft(data.astype(np.float64))) / len(data)
    frequencies = rfftfreq(len(data), 1 / SAMPLE_HZ)
    carrier_bin = round(coherent_hz / bin_hz)
    dbc = 20 * np.log10(np.maximum(amplitude / amplitude[carrier_bin], 1e-18))
    unwanted = amplitude.copy()
    unwanted[carrier_bin] = 0
    if sideband:
        mod_bin = round(60e6 / bin_hz)
        unwanted[mod_bin] = 0
    close = (abs(frequencies - coherent_hz) <= 10e6) & (unwanted > 0)
    close_bin = np.flatnonzero(close)[np.argmax(unwanted[close])]
    strongest = np.argsort(unwanted)[-10:][::-1]
    record = dict(method=method, requested_hz=frequency_hz,
                  simulated_hz=actual_hz, fft_bin_hz=bin_hz, sideband=sideband,
                  closest_analysis_offset_hz=bin_hz,
                  largest_nearby_spur_dbc=float(dbc[close_bin]),
                  largest_nearby_offset_hz=float(frequencies[close_bin]-coherent_hz),
                  strongest_spurs=[dict(frequency_hz=float(frequencies[k]),
                                        offset_hz=float(frequencies[k]-coherent_hz),
                                        dbc=float(dbc[k])) for k in strongest])
    return record, frequencies, dbc


def checks():
    # Full-circle amplitude/sign checks, including the +/-pi and quadrant joins.
    phases = np.arange(1 << 16, dtype=np.uint64) << 32
    ideal = np.exp(2j * np.pi * phases.astype(float) / PHASE_MODULUS)
    errors = {}
    for method in ("interpolated", "cordic24", "cordic18"):
        x, y, frac = sine_pair(phases, method)
        error = abs((x + 1j*y) / (1 << frac) - ideal)
        errors[method] = float(error.max())
        assert error.max() < 5e-5, (method, error.max())
    # At each update, preserve the next-word phase. Change only its slope and
    # lane rotations. Smallness of frequency changes is not needed for this.
    phase, previous_last = 0, None
    fcws = [round(f / SAMPLE_HZ * PHASE_MODULUS)
            for f in (800e6, 1.2e9, 1.200001e9, 1.3e9, 950e6)]
    old_fcw = fcws[0]
    for fcw in fcws:
        if previous_last is not None:
            assert (phase-previous_last) & PHASE_MASK == old_fcw
        last = (phase + (LANES-1)*fcw) & PHASE_MASK
        phase = (phase + LANES*fcw) & PHASE_MASK
        previous_last, old_fcw = last, fcw
    return errors


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("Maximum sine/cosine vector error:", checks(), flush=True)
    frames = 1 << 18
    results = []
    fig, axes = plt.subplots(2, 1, figsize=(10, 8), constrained_layout=True)
    for frequency_hz in (800e6, 1e9, 1.19999e9, 1.2e9, 1.20001e9, 1.3e9):
        for method in ("interpolated", "cordic24", "cordic18"):
            record, frequency, dbc = spectrum(frequency_hz, frames, method)
            results.append(record)
            print(json.dumps({k:v for k,v in record.items() if k != 'strongest_spurs'}), flush=True)
            if frequency_hz == 1.2e9:
                near = abs(frequency-frequency_hz) <= 10e6
                axes[0].plot((frequency[near]-frequency_hz)/1e6, dbc[near], label=method, lw=.7)
            if frequency_hz == 1.19999e9:
                near = abs(frequency-record['simulated_hz']) <= 10e6
                axes[1].plot((frequency[near]-record['simulated_hz'])/1e6, dbc[near], label=method, lw=.7)
    for ax, title in zip(axes, ('1.200000000 GHz', '1.1999896875 GHz (nearby FFT-coherent test)')):
        ax.set(title=title, xlabel='Offset from carrier [MHz]', ylabel='Discrete spur [dBc]',
               xlim=(-10, 10), ylim=(-170, -65))
        ax.grid(alpha=.3)
        ax.legend()
    fig.suptitle('Numerical shared DDS + lane rotations; 60 MHz tone also enabled\n'
                 '18-bit coefficients, final 16-bit rounding; excludes analog DAC/clock errors')
    fig.savefig(OUT/'near_carrier_spurs.png', dpi=160)
    (OUT/'results.json').write_text(json.dumps(dict(
        clock_hz=CLOCK_HZ, sample_hz=SAMPLE_HZ, frames=frames, results=results,
        limitations='Numerical design study, not AMD bit-accurate IP or RTL. '
                    'Frequencies snapped to 937.5 Hz grid; no claim for every tuning word. '
                    'Analog converter, clock, amplification, RFDC filter and ramp transients excluded.'), indent=2)+'\n')
    # Check neighborhoods where a folded carrier image or a 60 MHz lane image
    # can enter the +/-10 MHz band. These are not a uniform worst-case scan.
    boundaries = []
    for frequency_hz in (860.161e6, 983.041e6, 1043.041e6, 1105.921e6,
                         1168.801e6, 1228.801e6, 1288.801e6):
        record, _, _ = spectrum(frequency_hz, frames, 'cordic24')
        boundaries.append(record)
        print('Boundary:', json.dumps({k:v for k,v in record.items()
                                       if k != 'strongest_spurs'}), flush=True)
    (OUT/'fold_boundaries.json').write_text(json.dumps(boundaries, indent=2)+'\n')


if __name__ == '__main__':
    main()
