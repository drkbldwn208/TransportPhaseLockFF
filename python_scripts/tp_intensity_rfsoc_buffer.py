"""RFSoC TP intensity DMA buffer controller.

This file is intended to run on the RFSoC/PYNQ side.

It owns the PYNQ overlay handle, a persistent uint32 DMA buffer, and the
``axi_dma_6`` MM2S channel that feeds ``dwell_fcw_streamer_32_0``.

The controller is deliberately independent of ZMQ so it can also be imported
from a Jupyter notebook for direct testing.
"""

from __future__ import annotations

import time

import numpy as np


class TpIntensityBufferController:
    """Load TP intensity streamer words into a reusable PYNQ DMA buffer."""

    def __init__(
        self,
        *,
        bitfile=None,
        overlay=None,
        max_words=1_000_000,
        download_overlay=False,
        set_serial_mode=True,
    ):
        if overlay is None:
            if bitfile is None:
                raise ValueError("Provide either bitfile or an existing PYNQ overlay object")
            from pynq import Overlay

            print("TP buffer: attaching overlay", flush=True)
            overlay = Overlay(bitfile, download=download_overlay)

        from pynq import allocate

        print(f"TP buffer: allocating {int(max_words)} uint32 words", flush=True)
        self.overlay = overlay
        self.dma = overlay.axi_dma_6
        self.buffer = allocate(shape=(int(max_words),), dtype=np.uint32)
        self.max_words = int(max_words)
        self.loaded_words = 0
        self.loaded_metadata = {}

        print("TP buffer: resetting axi_dma_6 sendchannel", flush=True)
        self.reset()

        if set_serial_mode:
            print("TP buffer: selecting serial setpoint path", flush=True)
            self.select_serial_setpoint()
        print("TP buffer: ready", flush=True)

    def select_serial_setpoint(self):
        """Make setpoint_switch select dwell-streamer output.

        In setpoint_switch.v:

            sw_toggle=0 -> serial_setpoint
            sw_toggle=1 -> gpio_setpoint
        """

        self.overlay.axi_gpio_11.channel1.write(0, mask=0xFFFF)

    def select_gpio_setpoint(self):
        """Return setpoint_switch to manual GPIO setpoint mode."""

        self.overlay.axi_gpio_11.channel1.write(1, mask=0xFFFF)

    def dma_idle(self):
        return bool(self.dma.sendchannel.idle)

    def load_and_arm(self, words, metadata=None):
        """Copy words into the DMA buffer, flush, and start MM2S.

        Starting MM2S does not start the physical ramp immediately. The DMA
        will present data to the HLS streamer, but the streamer remains idle
        until its hardware start input receives the trigger pulse.
        """

        words = np.asarray(words, dtype=np.uint32)
        n_words = int(words.size)
        print(f"TP buffer: load_and_arm requested for {n_words} words", flush=True)
        if n_words <= 0:
            raise ValueError("empty TP intensity command array")
        if n_words > self.max_words:
            raise ValueError(f"{n_words} words received, max_words={self.max_words}")
        if not self.dma_idle():
            raise RuntimeError("axi_dma_6 sendchannel is busy")

        self.buffer[:n_words] = words
        self.buffer.flush()
        print("TP buffer: DMA buffer copied and flushed", flush=True)

        t0 = time.perf_counter()
        self.dma.sendchannel.transfer(self.buffer[:n_words])
        arm_time_ms = 1e3 * (time.perf_counter() - t0)
        print(f"TP buffer: axi_dma_6 MM2S armed in {arm_time_ms:.3f} ms", flush=True)

        self.loaded_words = n_words
        self.loaded_metadata = dict(metadata or {})
        return {
            "status": "ok",
            "message": "tp intensity DMA armed",
            "num_words": n_words,
            "num_bytes": int(n_words * 4),
            "arm_time_ms": arm_time_ms,
        }

    def wait_done(self, timeout_s=5.0, poll_s=0.005):
        """Poll until the MM2S transfer has completed.

        The transfer completes after the hardware trigger has arrived and the
        dwell streamer has consumed the whole command packet. This is useful in
        BLACS ``transition_to_manual`` as a sanity check that the ramp really
        played through.
        """

        start = time.perf_counter()
        timeout_s = float(timeout_s)
        print(f"TP buffer: wait_done timeout_s={timeout_s}", flush=True)
        while True:
            if self.dma_idle():
                elapsed_s = time.perf_counter() - start
                print(f"TP buffer: DMA done after {elapsed_s:.6f} s", flush=True)
                return {
                    "status": "ok",
                    "done": True,
                    "elapsed_s": elapsed_s,
                    "loaded_words": int(self.loaded_words),
                }
            if time.perf_counter() - start > timeout_s:
                elapsed_s = time.perf_counter() - start
                print(f"TP buffer: wait_done timed out after {elapsed_s:.6f} s", flush=True)
                return {
                    "status": "timeout",
                    "done": False,
                    "elapsed_s": elapsed_s,
                    "loaded_words": int(self.loaded_words),
                }
            time.sleep(float(poll_s))

    def status(self):
        return {
            "status": "ok",
            "loaded_words": int(self.loaded_words),
            "dma_idle": self.dma_idle(),
            "metadata": self.loaded_metadata,
        }

    def reset(self):
        """Force-stop a stuck MM2S transfer and return the channel to idle."""

        print("TP buffer: stopping axi_dma_6 sendchannel", flush=True)
        self.dma.sendchannel.stop()
        self.loaded_words = 0
        self.loaded_metadata = {}
        reply = {
            "status": "ok",
            "message": "axi_dma_6 sendchannel reset",
            "dma_idle": self.dma_idle(),
        }
        print(f"TP buffer: reset reply={reply}", flush=True)
        return reply
