"""Capture the Spectis Touch TCP configuration without triggering a measurement."""

import argparse
import socket
import time
from pathlib import Path


def capture(host, port=13000):
    received = bytearray()
    output_dir = Path(__file__).resolve().parent / "captures"
    output_dir.mkdir(exist_ok=True)
    output = output_dir / f"wifi-config-{time.time_ns()}.bin"
    try:
        with socket.create_connection((host, port), timeout=5) as connection:
            print(f"Connected to {host}:{port}", flush=True)
            connection.sendall(b'<request name="hi" client_name="python-spectis-probe" '
                               b'version="0.1" packages="true" />\n')
            connection.sendall(b'<request name="getconfig" />\n')
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                connection.settimeout(max(0.001, deadline - time.monotonic()))
                try:
                    chunk = connection.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                received.extend(chunk)
                if len(received) > 4 * 1024 * 1024:
                    raise RuntimeError("Response exceeded 4 MiB")
            try:
                connection.sendall(b'<request name="bye" />\n')
            except OSError:
                pass  # Preserve captured data if the instrument already closed.
    finally:
        if received:
            output.write_bytes(received)
            print(f"Saved {len(received)} bytes to {output}")
    if not received:
        raise RuntimeError("No configuration response received")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="IP address shown on the Spectis")
    parser.add_argument("--port", type=int, default=13000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    try:
        capture(args.host, args.port)
    except (OSError, RuntimeError) as exc:
        parser.exit(1, f"Wi-Fi probe failed: {exc}\n")


if __name__ == "__main__":
    main()
