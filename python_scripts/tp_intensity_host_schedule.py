"""Host-side TP intensity schedule encoder.

This file is intended to run on the Labscript/BLACS host PC.

Physical job:
    Read the compiled Labscript H5 shot file, extract the transverse-pump
    intensity analog schedule, and encode it into the 32-bit command words
    expected by the RFSoC dwell streamer.

RFSoC 32-bit command format:
    bits [31:16] = 16-bit TP intensity setpoint
    bits [15: 0] = dwell field

The current HLS streamer holds ordinary commands for ``dwell + 1`` PL clocks,
so a desired hold of N clocks is encoded as ``dwell = N - 1``.
"""

from __future__ import annotations

import json

import h5py
import numpy as np
import zmq

from labscript import IntermediateDevice
from labscript_devices.RedPitayaSPCM import tp_int_ramp

try:
    from blacs.device_base_class import DeviceTab, Worker
except Exception:  # Allows this file to be used outside BLACS for testing.
    DeviceTab = object
    Worker = object


PL_CLK_HZ = 245.76e6
MAX_DWELL_CYCLES = 2**16
DEFAULT_RFSoC_ENDPOINT = "tcp://192.168.1.154:5557"
DEFAULT_TIMEOUT_S = 5.0
DEFAULT_TP_INTENSITY_SCALE = 65535.0


class RFSOCTPIntensity(IntermediateDevice):
    """Dummy Labscript device for the RFSoC TP intensity streamer.

    This device has no direct outputs. It exists so the connection table can
    include an RFSoC TP intensity entry, causing BLACS to create a dedicated
    worker and run it once per shot.
    """

    description = "RFSoC transverse-pump intensity streamer"

    @classmethod
    def BLACS_tab(cls):
        return "labscript_devices.RFSOCTPIntensity.tp_intensity_host_schedule.RFSOCTPIntensityTab"

    @classmethod
    def BLACS_worker(cls):
        return "labscript_devices.RFSOCTPIntensity.tp_intensity_host_schedule.TpIntensityStreamerWorker"

    def __init__(
        self,
        name,
        parent_device,
        BLACS_connection=DEFAULT_RFSoC_ENDPOINT,
        **kwargs,
    ):
        self.BLACS_connection = BLACS_connection
        super().__init__(name, parent_device, **kwargs)

    def generate_code(self, h5_file):
        super().generate_code(h5_file)
        self.init_device_group(h5_file)


class RFSOCTPIntensityTab(DeviceTab):
    """BLACS tab for the RFSoC TP intensity streamer.

    There are intentionally no front-panel controls here. The tab exists to
    give BLACS a clean place to run the RFSoC worker during shot transitions.
    """

    def initialise_GUI(self):
        pass

    def initialise_workers(self):
        self.create_worker(
            "main_worker",
            TpIntensityStreamerWorker,
            {"connection": self.BLACS_connection},
        )
        self.primary_worker = "main_worker"

    def get_save_data(self):
        return {}

    def restore_save_data(self, save_data):
        pass


def intensity_to_u16(value, scale=DEFAULT_TP_INTENSITY_SCALE):
    """Map one compiled ramp value onto the RFSoC 16-bit setpoint bus.

    The conversion is intentionally simple and auditable:

        output_u16 = saturate(round(value * scale), 0, 65535)

    Set ``scale`` in runmanager based on the physical units of the compiled
    ramp. For example, if value is normalized 0..1, use scale=65535. If value is
    volts and 1 V should correspond to code 20000, use scale=20000.
    """

    if not np.isfinite(value):
        raise ValueError(f"non-finite TP intensity value: {value}")
    if not np.isfinite(scale):
        raise ValueError(f"non-finite TP intensity scale: {scale}")

    raw = int(round(float(value) * float(scale)))
    raw = min(max(raw, 0), 0xFFFF)
    return raw


def pack_streamer_word(intensity_u16, dwell_u16):
    """Pack one 32-bit TP intensity streamer command."""

    return np.uint32(((int(intensity_u16) & 0xFFFF) << 16) | (int(dwell_u16) & 0xFFFF))


def ramp_points_to_streamer_words(
    time_s,
    value,
    *,
    pl_clk_Hz=PL_CLK_HZ,
    intensity_scale=DEFAULT_TP_INTENSITY_SCALE,
    append_final_zero=True,
):
    """Convert sample-and-hold ramp points into packed uint32 commands.

    The compiled TP ramp is interpreted as:

        value[i] is held from time_s[i] to time_s[i+1].

    Duplicate-time points represent instantaneous jumps and are skipped because
    they have zero duration. Holds longer than 65536 PL clocks are split into
    repeated commands with the same setpoint.
    """

    time_s = np.asarray(time_s, dtype=np.float64)
    value = np.asarray(value, dtype=np.float32)
    n = min(len(time_s), len(value))
    time_s = time_s[:n]
    value = value[:n]

    words = []
    for i in range(n - 1):
        dt_s = float(time_s[i + 1] - time_s[i])
        if dt_s <= 0:
            continue

        hold_cycles = int(round(dt_s * float(pl_clk_Hz)))
        if hold_cycles <= 0:
            continue

        intensity_u16 = intensity_to_u16(value[i], scale=intensity_scale)

        while hold_cycles > 0:
            this_hold = min(hold_cycles, MAX_DWELL_CYCLES)
            words.append(pack_streamer_word(intensity_u16, this_hold - 1))
            hold_cycles -= this_hold

    if append_final_zero and words:
        # The final AXI word carries TLAST. The current HLS code has a one-clock
        # timing corner case for TLAST words, so make TLAST a harmless one-clock
        # return-to-zero command.
        words.append(pack_streamer_word(0, 0))

    return np.asarray(words, dtype=np.uint32)


def compiled_h5_to_streamer_words(
    h5_path,
    *,
    pl_clk_Hz=PL_CLK_HZ,
    intensity_scale=DEFAULT_TP_INTENSITY_SCALE,
):
    """Read a compiled Labscript H5 file and return ``(words, metadata)``.

    This is the main function to call from a BLACS worker during
    ``transition_to_buffered``.
    """

    with h5py.File(h5_path, "r") as h5file:
        ramp, ramp_metadata = tp_int_ramp.build_tp_int_ramp(h5file, max_points=None)

    if ramp is None:
        raise RuntimeError(f"No TP intensity ramp found in {h5_path}")

    time_s = np.asarray(ramp["time"], dtype=np.float64)
    value = np.asarray(ramp["value"], dtype=np.float32)
    words = ramp_points_to_streamer_words(
        time_s,
        value,
        pl_clk_Hz=pl_clk_Hz,
        intensity_scale=intensity_scale,
    )

    metadata = {
        "h5_path": str(h5_path),
        "num_ramp_points": int(len(time_s)),
        "num_words": int(words.size),
        "num_bytes": int(words.nbytes),
        "pl_clk_Hz": float(pl_clk_Hz),
        "intensity_scale": float(intensity_scale),
        "duration_s": float(time_s[-1] - time_s[0]) if len(time_s) else 0.0,
        "trigger_start_s": _metadata_float(ramp_metadata, "trigger_start"),
        "trigger_stop_s": _metadata_float(ramp_metadata, "trigger_stop"),
    }
    return words, metadata


def send_words_to_rfsoc(
    words,
    metadata,
    *,
    endpoint=DEFAULT_RFSoC_ENDPOINT,
    timeout_s=DEFAULT_TIMEOUT_S,
):
    """Send packed words to the RFSoC TP intensity ZMQ server.

    This small client helper is here so a BLACS worker can do:

        words, meta = compiled_h5_to_streamer_words(h5_path)
        reply = send_words_to_rfsoc(words, meta)
    """

    words = np.ascontiguousarray(words, dtype=np.uint32)
    header = {
        "cmd": "load_tp_intensity_words",
        "dtype": "uint32",
        "shape": list(words.shape),
        "num_words": int(words.size),
        "metadata": metadata,
    }

    context = zmq.Context.instance()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, int(timeout_s * 1000))
    socket.setsockopt(zmq.SNDTIMEO, int(timeout_s * 1000))
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(endpoint)

    try:
        socket.send_json(header, flags=zmq.SNDMORE)
        socket.send(words.tobytes())
        reply = socket.recv_json()
    finally:
        socket.close(0)

    if reply.get("status") != "ok":
        raise RuntimeError("Bad reply from RFSoC: " + json.dumps(reply))
    return reply


def get_rfsoc_status(*, endpoint=DEFAULT_RFSoC_ENDPOINT, timeout_s=DEFAULT_TIMEOUT_S):
    """Ask the RFSoC server whether its DMA channel is idle."""

    return _single_json_request(
        {"cmd": "get_status"},
        endpoint=endpoint,
        timeout_s=timeout_s,
    )


def wait_for_rfsoc_done(*, endpoint=DEFAULT_RFSoC_ENDPOINT, timeout_s=5.0):
    """Wait until the RFSoC reports that the TP intensity DMA finished."""

    return _single_json_request(
        {"cmd": "wait_done", "timeout_s": float(timeout_s)},
        endpoint=endpoint,
        timeout_s=timeout_s + 0.5,
    )


def _single_json_request(request, *, endpoint, timeout_s):
    context = zmq.Context.instance()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, int(timeout_s * 1000))
    socket.setsockopt(zmq.SNDTIMEO, int(timeout_s * 1000))
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(endpoint)
    try:
        socket.send_json(request)
        reply = socket.recv_json()
    finally:
        socket.close(0)
    return reply


def _metadata_float(metadata, key):
    if key not in metadata:
        return None
    return float(np.asarray(metadata[key]))


class TpIntensityStreamerWorker(Worker):
    """Optional BLACS worker for automatic TP ramp loading.

    This worker is independent of ``RpCounterWorker`` and is launched by
    ``RFSOCTPIntensityTab``. It reads the compiled shot H5 during
    ``transition_to_buffered``, uploads the packed command buffer to the RFSoC,
    and checks completion during ``transition_to_manual``.

    Suggested runmanager globals in ``RFSoC_TP_Params``:

        TP_INT_ENABLE        bool, default True
        TP_INT_SCALE         float, default 65535.0
        TP_INT_PL_CLK_HZ     float, default 245.76e6
        TP_INT_RFSoC_ENDPOINT string, default connection or DEFAULT_RFSoC_ENDPOINT
        TP_INT_DONE_TIMEOUT  float, default 5.0 s
    """

    def init(self):
        self._shot_h5_path = None
        self._dummy = str(getattr(self, "connection", "")).lower() in (
            "dummy",
            "sim",
            "simulation",
            "none",
        )
        self._enabled_for_shot = False
        self._done_timeout_s = 5.0
        self.endpoint = str(getattr(self, "connection", DEFAULT_RFSoC_ENDPOINT))
        if not self.endpoint or self.endpoint.lower() in ("dummy", "sim", "simulation", "none"):
            self.endpoint = DEFAULT_RFSoC_ENDPOINT
        print(f"TP intensity streamer worker initialized, endpoint={self.endpoint}, dummy={self._dummy}")

    def transition_to_buffered(self, device_name, h5_filepath, initial_values, fresh):
        self._shot_h5_path = h5_filepath

        with h5py.File(h5_filepath, "r+") as h5file:
            glbs = h5file["globals"]
            enabled = self._read_bool_global(glbs, "TP_INT_ENABLE", True)
            intensity_scale = self._read_float_global(
                glbs,
                "TP_INT_SCALE",
                DEFAULT_TP_INTENSITY_SCALE,
            )
            pl_clk_Hz = self._read_float_global(glbs, "TP_INT_PL_CLK_HZ", PL_CLK_HZ)
            endpoint = self._read_string_global(glbs, "TP_INT_RFSoC_ENDPOINT", self.endpoint)
            done_timeout_s = self._read_float_global(glbs, "TP_INT_DONE_TIMEOUT", 5.0)

            results = h5file.require_group("/results/tp_intensity_streamer")
            results.attrs["enabled"] = bool(enabled)
            results.attrs["endpoint"] = endpoint

        self._enabled_for_shot = bool(enabled)
        self._done_timeout_s = float(done_timeout_s)
        self.endpoint = endpoint

        if not enabled:
            print("TP intensity streamer disabled for this shot")
            return {}

        try:
            if not self._dummy:
                status = get_rfsoc_status(endpoint=endpoint)
                if status.get("status") != "ok" or not status.get("dma_idle", False):
                    raise RuntimeError(f"TP intensity RFSoC is not ready: {status}")

            words, metadata = compiled_h5_to_streamer_words(
                h5_filepath,
                pl_clk_Hz=pl_clk_Hz,
                intensity_scale=intensity_scale,
            )
            if self._dummy:
                reply = {
                    "status": "ok",
                    "message": "dummy TP intensity load",
                    "num_words": int(words.size),
                    "num_bytes": int(words.nbytes),
                }
            else:
                reply = send_words_to_rfsoc(words, metadata, endpoint=endpoint)

            with h5py.File(h5_filepath, "r+") as h5file:
                results = h5file.require_group("/results/tp_intensity_streamer")
                results.attrs["loaded"] = True
                results.attrs["num_words"] = int(words.size)
                results.attrs["num_bytes"] = int(words.nbytes)
                results.attrs["rfsoc_reply"] = json.dumps(reply)
                for key, value in metadata.items():
                    if value is not None:
                        results.attrs[key] = value

            print(
                f"TP intensity streamer loaded {words.size} words "
                f"({words.nbytes / 1e6:.3f} MB)"
            )

        except Exception as exc:
            with h5py.File(h5_filepath, "r+") as h5file:
                results = h5file.require_group("/results/tp_intensity_streamer")
                results.attrs["loaded"] = False
                results.attrs["error"] = str(exc)
            raise

        return {}

    def transition_to_manual(self):
        if self._enabled_for_shot and not self._dummy:
            reply = wait_for_rfsoc_done(
                endpoint=self.endpoint,
                timeout_s=self._done_timeout_s,
            )
            if reply.get("status") != "ok":
                print(f"TP intensity RFSoC did not report done: {reply}")
            else:
                print(f"TP intensity RFSoC done: {reply}")
        self._enabled_for_shot = False
        return True

    @staticmethod
    def _clean_global(raw):
        if isinstance(raw, bytes):
            raw = raw.decode()
        if isinstance(raw, np.generic):
            raw = raw.item()
        if isinstance(raw, str):
            return raw.split("#", 1)[0].strip()
        return raw

    @classmethod
    def _read_from_spcm_params(cls, glbs, name, default):
        for group_name in ("RFSoC_TP_Params", "SPCM_Params"):
            try:
                return cls._clean_global(glbs[group_name].attrs[name])
            except Exception:
                pass
        return default

    @classmethod
    def _read_bool_global(cls, glbs, name, default):
        raw = cls._read_from_spcm_params(glbs, name, default)
        if isinstance(raw, str):
            return raw.lower() not in ("", "0", "false", "off", "no", "none")
        return bool(raw)

    @classmethod
    def _read_float_global(cls, glbs, name, default):
        return float(cls._read_from_spcm_params(glbs, name, default))

    @classmethod
    def _read_string_global(cls, glbs, name, default):
        return str(cls._read_from_spcm_params(glbs, name, default))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Encode and optionally send a TP intensity ramp.")
    parser.add_argument("h5_path")
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--intensity-scale", type=float, default=DEFAULT_TP_INTENSITY_SCALE)
    parser.add_argument("--pl-clk-Hz", type=float, default=PL_CLK_HZ)
    parser.add_argument("--save-npy", default=None)
    args = parser.parse_args()

    words, meta = compiled_h5_to_streamer_words(
        args.h5_path,
        intensity_scale=args.intensity_scale,
        pl_clk_Hz=args.pl_clk_Hz,
    )
    print(meta)

    if args.save_npy:
        np.save(args.save_npy, words)
        print(f"Saved {words.size} words to {args.save_npy}")

    if args.endpoint:
        print(send_words_to_rfsoc(words, meta, endpoint=args.endpoint))
