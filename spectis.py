"""Direct Touch XML/TCP acquisition, verified against captured device responses."""
import re
import socket
import time
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from bridge import DeviceInfo, validate_info, validate_spectrum


@dataclass
class Measurement:
    info: DeviceInfo
    values: list
    status: dict
    xml: bytes
    received_at: float
    results: dict = field(default_factory=dict)
    y_unit: str = 'unknown'


def parse_measurement(raw, received_at):
    root = ET.fromstring(raw)
    status = {p.get('name'): p.text for p in root.findall('./status/parameter')}
    rows = root.findall('./data/row')
    coefficient = root.find('./data/coefficient_y')
    unit = coefficient.get('unit1') if coefficient is not None else None
    info = DeviceInfo(status.get('device type', ''), status.get('device serial number', ''),
                      tuple(float(r.attrib['wavelength']) for r in rows), unit)
    validate_info(info)
    values = validate_spectrum([r.attrib['value'] for r in rows], len(rows))
    results = {}
    for parameter in root.findall('./results/parameter'):
        try:
            value = float(parameter.text)
            if math.isfinite(value):
                results[parameter.get('name')] = value
        except (TypeError, ValueError):
            pass
    return Measurement(info, values, status, raw, received_at, results,
                       coefficient.get('unit2', 'unknown'))


class Spectis:
    def __init__(self, host, port=13000, on_activity=None):
        self.host, self.port = host, port
        self.sock = None
        self.buffer = bytearray()
        self.on_activity = on_activity

    def connect(self):
        self.buffer.clear()
        self.sock = socket.create_connection((self.host, self.port), timeout=5)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.send('<request name="hi" client_name="python-spectis" version="1.0" packages="true" />')
        self.read_element('config', 10)

    def check(self, cancel=None):
        self.send('<request name="getconfig" />')
        return self.read_element('config', 8, cancel)

    def send(self, xml):
        self.sock.sendall((xml + '\n').encode())

    def read_element(self, tag, timeout, cancel=None):
        pattern = re.compile(rb'<' + tag.encode() + rb'\b[^>]*>.*?</' + tag.encode() + rb'>', re.S)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                raise InterruptedError('Stopped; any in-progress exposure may still finish on the instrument')
            match = pattern.search(self.buffer)
            if match:
                raw = bytes(match.group())
                del self.buffer[:match.end()]
                return raw
            self.sock.settimeout(min(0.5, max(0.01, deadline-time.monotonic())))
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError('Instrument closed the connection')
            if self.on_activity:
                self.on_activity(time.monotonic())
            self.buffer.extend(chunk)
            if len(self.buffer) > 8*1024*1024:
                raise ValueError('Instrument response exceeded 8 MiB')
        raise TimeoutError(f'No complete {tag} response within {timeout:g} seconds')

    def measure(self, seconds=10, repeats=3, cancel=None):
        # Direct requests use microseconds; returned status confirmed 10000000 = 10 s.
        if not 0.0026 <= seconds <= 200 or not 1 <= repeats <= 250:
            raise ValueError('Exposure or repeat count outside instrument limits')
        self.send(f'<request name="measure" mode="direct" integration_time="{round(seconds*1e6)}" '
                  f'repeat_count="{repeats}" auto="off" beep="off" flicker_frequency="0" />')
        raw = self.read_element('measurement', seconds*repeats+30, cancel)
        import pylsl
        received_at = pylsl.local_clock()
        result = parse_measurement(raw, received_at)
        if int(result.status.get('repeat count', -1)) != repeats:
            raise ValueError('Instrument did not apply the requested repeat count')
        if abs(float(result.status.get('integration time', -1))-round(seconds*1e6)) > 1:
            raise ValueError('Instrument did not apply the requested exposure')
        return result

    def close(self):
        if self.sock:
            try:
                self.send('<request name="bye" />')
            except OSError:
                pass
            self.sock.close()
            self.sock = None


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument('host')
    args = parser.parse_args()
    device = Spectis(args.host)
    try:
        device.connect()
        print('Connected; requesting 10 seconds × 3 repeats', flush=True)
        start = time.monotonic()
        result = device.measure()
        folder = Path(__file__).resolve().parent/'captures'
        folder.mkdir(exist_ok=True)
        (folder/f'verified-three-repeats-{time.time_ns()}.xml').write_bytes(result.xml)
        print(f'{len(result.values)} channels in {time.monotonic()-start:.2f}s; '
              f'repeats={result.status["repeat count"]}; exposure={result.status["integration time"]} us')
    finally:
        device.close()
