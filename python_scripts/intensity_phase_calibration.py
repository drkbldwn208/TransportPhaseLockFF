"""INT2 phase alignment using the existing 30 kS/s phase-monitor DMA.

Use a stable positive DC signal at mixer IF, with optical feedback disabled.
ADC and LO frequency settings are left alone. I/Q averaging is in the FPGA,
BEFORE atan2; software uses a circular mean to retain phases near +/-pi.
"""
import time
import numpy as np

PHASE_CODES_PER_RAD = 8192.0


def read_phase(ol, samples=2048):
    """Read calibration phase [rad]; no changes to RF or feedback settings."""
    if ol.intensity_limits.read(8) != 0x494E5402:
        raise ValueError('Requires INT2 filtered receiver and matching HWH.')
    if not isinstance(samples, int) or not 64 <= samples <= 65536:
        raise ValueError('samples must be an integer in [64, 65536].')
    from pynq import allocate
    ol.axi_gpio_8.write(0, samples)
    dma = ol.axi_dma_4
    # The legacy packetizer's first packet after reset can have N+1 words.
    # Accept its actual byte count; subsequent packets have N words.
    buffer = allocate(shape=(samples+1,), dtype=np.int16)
    active = False
    try:
        if not dma.recvchannel.running:
            dma.recvchannel.start()
        dma.recvchannel.transfer(buffer)
        active = True
        deadline = time.monotonic()+samples/30000+2.0
        while not dma.recvchannel.idle:
            if dma.mmio.read(0x34) & 0x70:
                raise RuntimeError('Calibration DMA error.')
            if time.monotonic() > deadline:
                raise TimeoutError('Calibration DMA timeout; check RF clocks.')
            time.sleep(.001)
        dma.recvchannel.wait()
        active = False
        count = dma.recvchannel.transferred//2
        if count < 64:
            raise RuntimeError('Short calibration packet; repeat read_phase().')
        phase_rad = np.asarray(buffer[32:count], dtype=float)/PHASE_CODES_PER_RAD
        vector = np.mean(np.exp(1j*phase_rad))
        if abs(vector) < .95:
            raise RuntimeError('Calibration phase is moving; check DC input and LO/ADC frequencies.')
        return dict(phase_rad=float(np.angle(vector)), circular_concentration=float(abs(vector)),
                    phase_samples_rad=phase_rad.copy())
    finally:
        if active:
            dma.recvchannel.stop()
            dma.recvchannel.start()
        buffer.freebuffer()


def correct_phase(ol, residual_rad):
    """ADD a measured residual to the current LO correction; two's complement.

    This is a live phase change: run only during deliberate sensor calibration.
    Sign matches the existing LO CORDIC/mixer convention in this project.
    """
    if not np.isfinite(residual_rad):
        raise ValueError('Residual phase must be finite.')
    word = ol.axi_gpio_10.read(0) & 65535
    old_rad = (word-65536 if word & 32768 else word)/PHASE_CODES_PER_RAD
    new_rad = (old_rad+residual_rad+np.pi)%(2*np.pi)-np.pi
    word = int(round(new_rad*PHASE_CODES_PER_RAD)) & 65535
    ol.axi_gpio_10.channel1.write(word, mask=65535)
    time.sleep(.02)  # slow I/Q CIC settles in about 0.1 ms
    return float(new_rad)
