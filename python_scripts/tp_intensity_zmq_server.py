#!/usr/bin/env python3
"""RFSoC ZMQ server for TP intensity ramp loading.

This file is intended to run as a background process on the RFSoC.

It receives packed uint32 command words from the Labscript/BLACS host and
delegates all overlay/DMA work to ``TpIntensityBufferController``.
"""

from __future__ import annotations

import json

import numpy as np
import zmq

from tp_intensity_rfsoc_buffer import TpIntensityBufferController


DEFAULT_ENDPOINT = "tcp://*:5557"


def run_server(*, bitfile, endpoint=DEFAULT_ENDPOINT, max_words=1_000_000, download_overlay=False):
    """Start the RFSoC TP intensity loader server."""

    controller = TpIntensityBufferController(
        bitfile=bitfile,
        max_words=max_words,
        download_overlay=download_overlay,
        set_serial_mode=True,
    )

    context = zmq.Context.instance()
    socket = context.socket(zmq.REP)
    socket.bind(endpoint)
    print(f"TP intensity RFSoC server listening on {endpoint}", flush=True)

    while True:
        print("TP server: waiting for request", flush=True)
        parts = socket.recv_multipart()
        try:
            request = json.loads(parts[0].decode())
            cmd = request.get("cmd")
            print(f"TP server: received cmd={cmd!r} frames={len(parts)}", flush=True)

            if cmd == "get_status":
                reply = controller.status()
                print(f"TP server: get_status reply={reply}", flush=True)
                socket.send_json(reply)
                continue

            if cmd == "wait_done":
                timeout_s = float(request.get("timeout_s", 5.0))
                reply = controller.wait_done(timeout_s=timeout_s)
                print(f"TP server: wait_done reply={reply}", flush=True)
                socket.send_json(reply)
                continue

            if cmd == "reset":
                reply = controller.reset()
                print(f"TP server: reset reply={reply}", flush=True)
                socket.send_json(reply)
                continue

            if cmd != "load_tp_intensity_words":
                reply = {"status": "error", "message": f"unknown cmd {cmd!r}"}
                print(f"TP server: error reply={reply}", flush=True)
                socket.send_json(reply)
                continue

            if len(parts) != 2:
                raise RuntimeError("expected JSON header plus raw uint32 payload")
            if request.get("dtype") != "uint32":
                raise RuntimeError(f"expected dtype uint32, got {request.get('dtype')}")

            words = np.frombuffer(parts[1], dtype=np.uint32)
            print(
                f"TP server: loading {words.size} words ({words.nbytes} bytes)",
                flush=True,
            )
            reply = controller.load_and_arm(words, metadata=request.get("metadata", {}))
            print(f"TP server: load reply={reply}", flush=True)
            socket.send_json(reply)

        except Exception as exc:
            reply = {"status": "error", "message": str(exc)}
            print(f"TP server: exception reply={reply}", flush=True)
            socket.send_json(reply)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bitfile", required=True)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--max-words", type=int, default=1_000_000)
    parser.add_argument(
        "--download",
        action="store_true",
        help="Program the FPGA before starting the server. Default is attach-only.",
    )
    args = parser.parse_args()

    run_server(
        bitfile=args.bitfile,
        endpoint=args.endpoint,
        max_words=args.max_words,
        download_overlay=args.download,
    )
