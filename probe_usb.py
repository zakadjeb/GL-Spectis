"""List USB devices or capture the Touch configuration via bundled ADB.

Experimental transport probe based on the supplied Spectrosoft Touch plugin.
Does not trigger measurements, install drivers, or modify device configuration.
"""

import argparse
from pathlib import Path
import socket
import subprocess
import time


ROOT = Path(__file__).resolve().parent
DEFAULT_ADB = ROOT / "vendor_inspection/spectrosoft/app/adb/adb.exe"


def run_adb(executable, *arguments):
    result = subprocess.run([str(executable), *arguments], capture_output=True,
                            text=True, timeout=15)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, default=DEFAULT_ADB)
    parser.add_argument("--serial", help="ADB serial of the Spectis to probe")
    parser.add_argument("--probe", action="store_true", help="Capture configuration response")
    parser.add_argument("--port", type=int, default=21300, help="Local forwarded TCP port")
    args = parser.parse_args()
    if not args.adb.is_file():
        parser.error("ADB executable not found; supply --adb PATH")
    if not 1024 <= args.port <= 65535:
        parser.error("Local port must be between 1024 and 65535")
    if args.probe and not args.serial:
        parser.error("--probe requires the Spectis --serial from the device list")
    try:
        listing = run_adb(args.adb, "devices", "-l")
        print(listing)
        if not args.probe:
            return
        devices = [line.split() for line in listing.splitlines()
                   if line.strip() and not line.startswith("List of devices")]
        if not any(len(row) >= 2 and row[0] == args.serial and row[1] == "device"
                   for row in devices):
            raise RuntimeError("Selected Spectis is not connected/authorized in ADB")
        local = f"tcp:{args.port}"
        mappings = run_adb(args.adb, "forward", "--list")
        if any(local in line.split() for line in mappings.splitlines()):
            raise RuntimeError("Local port already forwarded; choose another --port")
        # Also refuse to take a port already occupied by a non-ADB application.
        with socket.socket() as check:
            check.bind(("127.0.0.1", args.port))
        run_adb(args.adb, "-s", args.serial, "forward", local, "tcp:13000")
        try:
            output_dir = ROOT / "captures"
            output_dir.mkdir(exist_ok=True)
            output = output_dir / f"config-{time.time_ns()}.bin"
            received = bytearray()
            try:
                with socket.create_connection(("127.0.0.1", args.port), timeout=5) as connection:
                    # These request names and package mode appear in stplugin.dll.
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
                            raise RuntimeError("Probe response exceeded 4 MiB")
                    connection.sendall(b'<request name="bye" />\n')
            finally:
                if received:
                    output.write_bytes(received)
                    print(f"Saved {len(received)} response bytes to {output}")
            if not received:
                raise RuntimeError("No response: check the instrument app and USB connection")
        finally:
            run_adb(args.adb, "-s", args.serial, "forward", "--remove", local)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"USB probe failed: {exc}\n")


if __name__ == "__main__":
    main()
