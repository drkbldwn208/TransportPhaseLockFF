"""Exact-period 570 MHz complex and 60 MHz real waveforms at the existing rates.

All lanes advance together at 245.76 MHz. The complete waveform repeats after
1024 fabric clocks, eliminating phase-accumulator frequency rounding.
"""
from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'TransportPhaseLockFF.srcs/sources_1/new'
FS_HZ = 245_760_000


def write_rom(name, frequency_hz, lanes, length):
    for lane in range(lanes):
        values = []
        for frame in range(length):
            angle = 2 * math.pi * frequency_hz / FS_HZ * (frame + lane / lanes)
            cosine = round(32767 * math.cos(angle))
            sine = round(32767 * math.sin(angle))
            values.append(f'{((sine & 65535) << 16) | (cosine & 65535):08x}\n')
        (DEST / f'pdh_{name}_{lane}.mem').write_text(''.join(values))


if __name__ == '__main__':
    write_rom('offset', 570_000_000, 7, 1024)
    write_rom('reference', 60_000_000, 8, 512)
