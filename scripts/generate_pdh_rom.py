"""Generate the quarter-wave table shared by all direct PDH DDS ROM copies.

4096 midpoint samples in [0, pi/2], signed 16-bit amplitude with peak 32767.
The RTL handles quadrants and signs; it reads the same data file into 18 copies.
"""
from pathlib import Path
import math

root = Path(__file__).resolve().parents[1]
output = root / 'TransportPhaseLockFF.srcs/sources_1/new/pdh_quarter_cos.mem'
values = [round(32767 * math.cos((k + 0.5) * math.pi / 8192)) for k in range(4096)]
assert all(a >= b for a, b in zip(values, values[1:]))
assert values[0] == 32767 and values[-1] >= 0
text = ''.join(f'{value:04x}\n' for value in values)
# Do not touch the file during a build when the contents already match.
if not output.exists() or output.read_text() != text:
    output.write_text(text)
print(f'{output}: {len(values)} words, 16 bits; 18 dual-port RTL copies')
