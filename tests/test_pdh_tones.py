"""Current PDH3 DDS and photon-counter simulation entry point.

The earlier fixed-period PDH2 testbench is historical. PDH3 is checked against
frequency-word arithmetic and direct cosine evaluation by the following test.
"""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('test_pdh_direct_photon.py')), run_name='__main__')
