#!/usr/bin/env python3
"""RFSoC ZMQ server for TP intensity ramp loading.

This file is intended to run as a background process on the RFSoC.

It accepts trigger-relative times in seconds and optical power in mW, or
explicitly labelled legacy packed commands. Conversion happens before arming.
"""

from __future__ import annotations

import json

import numpy as np
import zmq

from tp_intensity_rfsoc_buffer import TpIntensityBufferController


DEFAULT_ENDPOINT = "tcp://*:5557"


def load_request(controller, request, payload):
    """Decode an explicit wire format; never reinterpret ADC codes as mW."""
    if request['cmd'] == 'load_tp_intensity_power':
        shape = request.get('shape', [])
        if (request.get('dtype') != '<f8' or request.get('time_units') != 's' or
                request.get('power_units') != 'mW' or len(shape) != 2 or
                shape[1] != 2 or not isinstance(shape[0], int) or shape[0] < 2 or
                len(payload) != shape[0]*16):
            raise ValueError('Expected <f8 N-by-2 [trigger-relative time_s, power_mW] payload.')
        points = np.frombuffer(payload, dtype='<f8').reshape(shape)
        return controller.load_power_and_arm(points[:, 0], points[:, 1],
            sensor_mode=request.get('sensor_mode'), metadata=request.get('metadata', {}))
    if request['cmd'] == 'load_tp_intensity_words':
        if request.get('dtype') != 'uint32' or len(payload) % 4:
            raise ValueError('Expected uint32 packed-command payload.')
        words = np.frombuffer(payload, dtype='<u4')
        return controller.load_and_arm(words, metadata=request.get('metadata', {}))
    raise ValueError(f"Unknown load command {request['cmd']!r}")


def run_server(*, bitfile, endpoint=DEFAULT_ENDPOINT, max_words=1_000_000,
               download_overlay=False, shot_recording=None, servo_configuration=None):
    """Start the RFSoC TP intensity loader server."""

    controller = TpIntensityBufferController(
        bitfile=bitfile,
        max_words=max_words,
        download_overlay=download_overlay,
        set_serial_mode=True,
        shot_recording=shot_recording,
        servo_configuration=servo_configuration,
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

            if cmd not in ("load_tp_intensity_words", "load_tp_intensity_power"):
                reply = {"status": "error", "message": f"unknown cmd {cmd!r}"}
                print(f"TP server: error reply={reply}", flush=True)
                socket.send_json(reply)
                continue

            if len(parts) != 2:
                raise RuntimeError("expected JSON header plus binary payload")
            reply = load_request(controller, request, parts[1])
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
    parser.add_argument('--shot-recording-json',
                        help='Optional JSON file: directory, decimation_log2, tail_s, power_per_code and metadata.')
    parser.add_argument('--servo-configuration-json',
                        help='Current servo.configuration(ol) snapshot from the same FPGA/table-loading session.')
    parser.add_argument(
        "--download",
        action="store_true",
        help="Program the FPGA before starting the server. Default is attach-only.",
    )
    args = parser.parse_args()
    shot_recording = None
    if args.shot_recording_json:
        from pathlib import Path
        shot_recording = json.loads(Path(args.shot_recording_json).read_text())
    servo_configuration = None
    if args.servo_configuration_json:
        from pathlib import Path
        servo_configuration = json.loads(Path(args.servo_configuration_json).read_text())

    run_server(
        bitfile=args.bitfile,
        endpoint=args.endpoint,
        max_words=args.max_words,
        download_overlay=args.download,
        shot_recording=shot_recording,
        servo_configuration=servo_configuration,
    )
