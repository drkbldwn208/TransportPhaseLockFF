"""Simulate the isolated RTL outline, without opening/modifying the project."""
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT/'rtl_candidates/pdh_tunable'
WORK = ROOT/'build/pdh_tunable_outline'
BIN = Path('/home/levlabcukomen/tools/Vivado/2024.1/bin')
sys.path.insert(0, str(SRC))
from coefficients import configuration_words, SIDEBAND_RATIO

profiles = [dict(carrier_hz=1.2e9, reference_phase_deg=150),
            dict(carrier_hz=1.200001e9, reference_phase_deg=330),
            dict(carrier_hz=800e6, reference_phase_deg=-90),
            dict(carrier_hz=1.3e9, reference_phase_deg=0)]
WORK.mkdir(parents=True, exist_ok=True)
words = []
frequencies = []
for profile in profiles:
    data, frequency = configuration_words(**profile)
    words.extend(data)
    frequencies.append(frequency)
(WORK/'pdh_tunable_configs.mem').write_text(''.join(f'{v:08x}\n' for v in words))
for command in (
    ['xvlog', '--sv', *map(str, sorted(SRC.glob('*.sv'))), str(ROOT/'tests/pdh_tunable_outline_tb.sv')],
    ['xelab', 'pdh_tunable_outline_tb', '-s', 'pdh_tunable'],
    ['xsim', 'pdh_tunable', '-runall'],
):
    result = subprocess.run([str(BIN/command[0]), *command[1:]], cwd=WORK,
                            capture_output=True, text=True)
    (WORK/(command[0]+'.log')).write_text(result.stdout+result.stderr)
    if result.returncode or 'Fatal:' in result.stdout:
        raise RuntimeError((result.stdout+result.stderr)[-6000:])
assert 'PASS: phase continuity' in result.stdout


def unpack(hex_word, lanes):
    word = int(hex_word, 16)
    result = np.array([(word >> (16*k)) & 65535 for k in range(lanes)])
    return np.where(result >= 32768, result-65536, result)


def angle(hex_word):
    value = int(hex_word, 16)
    if value & (1 << 25):
        value -= 1 << 26
    return value * np.pi / (1 << 23)


rows = [line.split() for line in (WORK/'pdh_tunable_samples.txt').read_text().splitlines()]
max_error = 0
profiles_checked = set()
# Seven clock behavioral CORDIC + multiplier/add/add/output pipeline. The
# trace captures inputs before the edge and DAC outputs after the same edge.
delay = 10
for index in range(delay, len(rows)):
    source, output = rows[index-delay], rows[index]
    profile = int(source[3])
    summed, reference = unpack(output[4], 14), unpack(output[5], 8)
    if profile < 0:
        assert not summed.any() and not reference.any()
        continue
    profiles_checked.add(profile)
    carrier_phase, modulation_phase = angle(source[1]), angle(source[2])
    k, r = np.arange(14), np.arange(8)
    ac, am, ar = round(.55*32767), round(.55*SIDEBAND_RATIO*32767), round(.1*32767)
    expected_sum = ac*np.cos(carrier_phase+2*np.pi*frequencies[profile]/(14*245.76e6)*k)
    expected_sum += am*np.cos(modulation_phase+2*np.pi*60e6/(14*245.76e6)*k)
    expected_ref = ar*np.cos(modulation_phase+2*np.pi*60e6/(8*245.76e6)*r+
                             np.deg2rad(profiles[profile]['reference_phase_deg']))
    error = max(abs(summed-expected_sum).max(), abs(reference-expected_ref).max())
    assert error < 2, (index, profile, error, summed[:2], expected_sum[:2])
    max_error = max(max_error, error)
assert profiles_checked == {0, 1, 2, 3}
print(f'PASS: {len(rows)-delay} sample words, 4 frequencies/reference phases; '
      f'maximum physical-waveform error {max_error:.3f} DAC counts.')
print('Behavioral CORDIC only; no vendor IP, synthesis, routing or board validation.')
