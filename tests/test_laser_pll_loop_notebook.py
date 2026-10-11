"""Execute the sweep notebook with register mocks; never program board hardware."""
import contextlib
import io
import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('MPLCONFIGDIR', '/tmp/laser_loop_notebook_matplotlib')
import matplotlib
matplotlib.use('Agg')
import numpy as np

from test_laser_pll_loop_sweep import Analyzer, fra

ROOT = Path(__file__).resolve().parents[1]


def run():
    fixture = Analyzer()
    fixture.setUp()
    ol = fixture.ol
    # Emulate a stable integrator loop with a high-frequency pole. Exercise the
    # notebook's actual register/phasor conversion, CSV output and plotting.
    original_write = ol.pll_fra.write
    def write(offset, value):
        original_write(offset, value)
        if not value:
            return
        frequency_hz = ol.pll_fra_tone.read(0x10) * 8*fra.FS_HZ / 2**32
        loop = (20000/(1j*frequency_hz)) / (1+1j*frequency_hz/200000)
        injection = ol.pll_fra_tone.read(0x18)
        drive = injection/(1+loop)
        n = ol.pll_fra_window.read(8)
        for ip, phasor in ((ol.pll_fra_error, -loop*drive), (ol.pll_fra_drive, drive)):
            for address, amplitude in ((0x20, phasor.real), (0x40, phasor.imag)):
                bits = round(amplitude*n*32768/2) & ((1<<72)-1)
                for k in range(3):
                    ip.values[address+4*k] = (bits>>(32*k)) & 0xFFFFFFFF
    ol.pll_fra.write = write

    def capture_iq(ol, samples, decimation_log2):
        fs_hz = fra.FS_HZ / 2**decimation_log2
        time_s = np.arange(samples)/fs_hz
        z = 5000*np.exp(1j*0.02*np.sin(2*np.pi*1000*time_s))
        return dict(i_adc_counts=z.real, q_adc_counts=z.imag,
                    sample_rate_hz=fs_hz, decimation_log2=decimation_log2)

    output = Path('/tmp/laser_pll_loop_notebook_test')
    output.mkdir(exist_ok=True)
    cells = json.loads((ROOT/'python_scripts/laser_pll_loop_sweep.ipynb').read_text())['cells']
    namespace = {'ol': ol}
    old_directory = Path.cwd()
    try:
        os.chdir(output)
        with patch.object(fra.time, 'sleep', lambda _: None), contextlib.redirect_stdout(io.StringIO()):
            for k, cell in enumerate(cells):
                if cell['cell_type'] != 'code':
                    continue
                # Import/reload is intentionally executed before replacing the
                # independent DMA capture call with a known numerical vector.
                if k == 12:
                    with patch.object(fra.laser_pll, 'capture_iq', capture_iq):
                        exec(compile(''.join(cell['source']), f'loop notebook cell {k}', 'exec'), namespace)
                else:
                    exec(compile(''.join(cell['source']), f'loop notebook cell {k}', 'exec'), namespace)
        assert len(namespace['rows']) == 61
        assert len(namespace['csv_path'].read_text().splitlines()) == 62
        assert namespace['raw_path'].exists() and namespace['psd_path'].exists()
        assert ol.pll_control.read(0) == 1, 'Feedback must stay enabled'
        assert ol.pll_fra.read(0) == 0 and ol.pll_fra_tone.read(0x18) == 0
        print(f'PASS: all {sum(c["cell_type"]=="code" for c in cells)} sweep notebook code cells; CSV/NPZ/plots in {output}; feedback unchanged')
    finally:
        os.chdir(old_directory)


if __name__ == '__main__':
    run()
