"""Exact-period real 1.2 GHz + 60 MHz waveforms for DAC230/0, and 60 MHz LO.

All lanes advance together at 245.76 MHz. The complete waveform repeats after
512 fabric clocks, eliminating phase-accumulator frequency rounding.
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
    for lane in range(14):
        values = []
        for frame in range(512):
            time_s = (frame + lane/14) / FS_HZ
            carrier = round(32767*math.cos(2*math.pi*1_200_000_000*time_s))
            modulation = round(32767*math.cos(2*math.pi*60_000_000*time_s))
            values.append(f'{((modulation & 65535) << 16) | (carrier & 65535):08x}\n')
        (DEST / f'pdh_sum_{lane}.mem').write_text(''.join(values))
    write_rom('reference', 60_000_000, 8, 512)
