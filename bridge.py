"""Stream spectra to LSL. Hardware acquisition requires a model-specific adapter."""

import argparse
import importlib
import math
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceInfo:
    model: str
    serial: str
    wavelengths_nm: tuple[float, ...]
    unit: str  # Exact SDK quantity/unit, e.g. calibrated spectral irradiance.


def validate_info(info):
    if not info.model or not info.serial or not info.unit:
        raise ValueError("Device model, serial number and physical unit are required")
    wavelengths = info.wavelengths_nm
    if not wavelengths or any(not math.isfinite(w) or w <= 0 for w in wavelengths):
        raise ValueError("Wavelengths must be finite, positive and nonempty")
    if any(a >= b for a, b in zip(wavelengths, wavelengths[1:])):
        raise ValueError("Wavelengths must be strictly increasing")


def validate_spectrum(values, channel_count):
    values = [float(value) for value in values]
    if len(values) != channel_count:
        raise ValueError("Spectrum length changed; stopping to avoid mislabeled channels")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Spectrum contains nonfinite values")
    return values


class DemoDevice:
    """Synthetic data only; this class never accesses USB."""

    def __enter__(self):
        self.info = DeviceInfo("SIMULATED", "demo", tuple(range(380, 781, 5)), "a.u.")
        return self

    def read_spectrum(self):
        time.sleep(0.05)
        amplitude = 1 + 0.1 * math.sin(time.monotonic())
        return [amplitude * math.exp(-0.5 * ((w - 550) / 40) ** 2)
                for w in self.info.wavelengths_nm]

    def __exit__(self, *args):
        pass


def make_outlet(info, demo, lsl):
    validate_info(info)
    name = "GL-Spectis-DEMO" if demo else "GL-Spectis"
    stream = lsl.StreamInfo(name, "Spectrum", len(info.wavelengths_nm),
                            lsl.IRREGULAR_RATE, "double64",
                            f"gl-spectis:{info.model}:{info.serial}:spectrum")
    desc = stream.desc()
    desc.append_child_value("manufacturer", "Synthetic" if demo else "GL Optic")
    desc.append_child_value("model", info.model)
    desc.append_child_value("serial_number", info.serial)
    desc.append_child_value("simulated", str(demo).lower())
    desc.append_child_value("timestamp_source", "host_lsl_clock_after_sdk_read")
    desc.append_child_value("timestamp_note", "Receipt time, not optical exposure time")
    channels = desc.append_child("channels")
    for wavelength in info.wavelengths_nm:
        channel = channels.append_child("channel")
        channel.append_child_value("label", f"{wavelength:g} nm")
        channel.append_child_value("type", "Spectrum")
        channel.append_child_value("unit", info.unit)
        channel.append_child_value("wavelength_nm", str(wavelength))
    return lsl.StreamOutlet(stream)


def positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true", help="Stream synthetic spectra only")
    mode.add_argument("--adapter", metavar="MODULE", help="SDK adapter module exposing open_device()")
    parser.add_argument("--max-rate", type=positive_number, default=1,
                        help="Maximum acquisition attempts per second (default: 1)")
    parser.add_argument("--duration", type=positive_number, help="Stop after this many seconds")
    args = parser.parse_args()
    try:
        import pylsl
    except (ImportError, RuntimeError) as exc:
        parser.exit(1, f"Cannot load pylsl: {exc}\nInstall requirements.txt first.\n")
    try:
        device_context = (DemoDevice() if args.demo else
                          importlib.import_module(args.adapter).open_device())
        with device_context as device:
            info = device.info
            outlet = make_outlet(info, args.demo, pylsl)
            print(f"Streaming {'DEMO' if args.demo else info.model}: "
                  f"{len(info.wavelengths_nm)} channels. Ctrl+C stops.", flush=True)
            started = time.monotonic()
            count = 0
            while args.duration is None or time.monotonic() - started < args.duration:
                cycle_started = time.monotonic()
                values = device.read_spectrum()
                received_at = pylsl.local_clock()
                values = validate_spectrum(values, len(info.wavelengths_nm))
                outlet.push_sample(values, received_at)
                count += 1
                delay = max(0, 1 / args.max_rate - (time.monotonic() - cycle_started))
                if args.duration is not None:
                    delay = min(delay, max(0, args.duration - (time.monotonic() - started)))
                time.sleep(delay)
            print(f"Published {count} spectra.")
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as exc:
        parser.exit(1, f"Streaming stopped: {exc}\n")


if __name__ == "__main__":
    main()
