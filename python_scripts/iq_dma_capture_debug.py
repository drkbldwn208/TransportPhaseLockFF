"""Debug helper for the post-decimation I/Q DMA capture path.

Run this on the PYNQ target, not on the development host.  It assumes the
overlay exposes:

  * axi_gpio_13.channel1: derotator enable
  * axi_gpio_13.channel2: TLAST packet length in 128-bit output beats
  * axi_dma_3: S2MM-only AXI DMA for packed {I64,Q64} samples
"""

import time
import gc

import numpy as np
from pynq import allocate


DMA_STATUS_BITS = {
    0: "Halted",
    1: "Idle",
    3: "SGIncld",
    4: "DMAIntErr",
    5: "DMASlvErr",
    6: "DMADecErr",
    8: "SGIntErr",
    9: "SGSlvErr",
    10: "SGDecErr",
    12: "IOC_Irq",
    13: "Dly_Irq",
    14: "Err_Irq",
}


def decode_dma_status(status):
    value = int(status)
    flags = [name for bit, name in DMA_STATUS_BITS.items() if value & (1 << bit)]
    return f"0x{value:08x} ({', '.join(flags) if flags else 'no flags'})"


def setup_iq_buffer(duration_s, sample_rate_hz):
    samples = int(round(duration_s * sample_rate_hz))
    print(f"Allocating {samples} packed I/Q beats ({samples * 16 / 1e6:.2f} MB)")
    return allocate(shape=(samples, 2), dtype=np.int64)


def release_buffer(dma_buffer):
    """Release a PYNQ BO promptly in notebook workflows."""

    try:
        dma_buffer.freebuffer()
    except AttributeError:
        pass
    gc.collect()


def execute_iq_capture(overlay, dma_buffer, enable_derotation=True, toggle_enable=True):
    sample_count = int(dma_buffer.shape[0])
    dma = overlay.axi_dma_3
    gpio = overlay.axi_gpio_13

    if toggle_enable:
        gpio.channel1.write(0, mask=0x1)
    else:
        gpio.channel1.write(1 if enable_derotation else 0, mask=0x1)
    gpio.channel2.write(sample_count, mask=0xFFFFFFFF)

    dma_buffer[:] = 0
    dma_buffer.flush()

    status_before = dma.register_map.S2MM_DMASR
    print("S2MM before:", decode_dma_status(status_before))
    if int(status_before) & (1 << 3):
        raise RuntimeError(
            "axi_dma_3 is built with scatter-gather enabled. Rebuild it with "
            "c_include_sg=0 for PYNQ recvchannel.transfer(buffer)."
        )

    dma.recvchannel.transfer(dma_buffer)
    print("DMA armed")

    if toggle_enable:
        time.sleep(0.001)
        gpio.channel1.write(1 if enable_derotation else 0, mask=0x1)
    dma.recvchannel.wait()
    dma_buffer.invalidate()

    status_after = dma.register_map.S2MM_DMASR
    print("S2MM after: ", decode_dma_status(status_after))
    print("nonzero int64 words:", int(np.count_nonzero(dma_buffer)))
    print("first rows:\n", dma_buffer[:8])
    print("last rows:\n", dma_buffer[-8:])
    return dma_buffer


def split_iq_columns(dma_buffer):
    """Return I and Q arrays from the current axis_tlast_gen_iq packing."""

    q_data = dma_buffer[:, 0]
    i_data = dma_buffer[:, 1]
    return i_data, q_data


def capture_iq_chunks_to_hdf5(
    overlay,
    output_path,
    total_samples,
    sample_rate_hz,
    chunk_samples=262_144,
    enable_derotation=True,
    compression="gzip",
    compression_opts=4,
):
    """Capture a long trace without allocating one giant contiguous buffer.

    XRT/PYNQ buffers are physically contiguous BOs.  A 30 MB allocation can fail
    after a notebook has allocated and freed several buffers because the memory
    pool is fragmented.  This function keeps the live BO small and streams each
    chunk into an HDF5 dataset.
    """

    import h5py

    total_samples = int(total_samples)
    chunk_samples = int(chunk_samples)
    if total_samples <= 0:
        raise ValueError("total_samples must be positive")
    if chunk_samples <= 0:
        raise ValueError("chunk_samples must be positive")

    gpio = overlay.axi_gpio_13
    gpio.channel1.write(1 if enable_derotation else 0, mask=0x1)

    with h5py.File(output_path, "w") as h5:
        dset = h5.create_dataset(
            "iq",
            shape=(total_samples, 2),
            dtype=np.int64,
            chunks=(min(chunk_samples, total_samples), 2),
            compression=compression,
            compression_opts=compression_opts,
        )
        h5.attrs["sample_rate_hz"] = float(sample_rate_hz)
        h5.attrs["column0"] = "Q_lower_64_bits"
        h5.attrs["column1"] = "I_upper_64_bits"

        offset = 0
        while offset < total_samples:
            this_chunk = min(chunk_samples, total_samples - offset)
            print(f"capturing {offset}:{offset + this_chunk} / {total_samples}")

            dma_buffer = allocate(shape=(this_chunk, 2), dtype=np.int64)
            try:
                execute_iq_capture(
                    overlay,
                    dma_buffer,
                    enable_derotation=enable_derotation,
                    toggle_enable=False,
                )
                dset[offset : offset + this_chunk, :] = np.asarray(dma_buffer)
                h5.flush()
            finally:
                release_buffer(dma_buffer)

            offset += this_chunk

    return output_path


def capture_iq_duration_to_hdf5(
    overlay,
    output_path,
    duration_s,
    sample_rate_hz,
    chunk_samples=262_144,
    enable_derotation=True,
):
    total_samples = int(round(duration_s * sample_rate_hz))
    return capture_iq_chunks_to_hdf5(
        overlay=overlay,
        output_path=output_path,
        total_samples=total_samples,
        sample_rate_hz=sample_rate_hz,
        chunk_samples=chunk_samples,
        enable_derotation=enable_derotation,
    )
