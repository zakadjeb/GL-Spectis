import socket
import threading
import unittest
from spectis import Spectis, parse_measurement

XML = b'''<measurement><status>
<parameter name="device type">Spectis test</parameter>
<parameter name="device serial number">test-only</parameter>
<parameter name="repeat count">3</parameter>
<parameter name="integration time">10000000</parameter>
</status><data><coefficient_y unit1="mW/m^2/nm"/>
<row wavelength="400" value="-0.1"/><row wavelength="500" value="2.3"/>
</data></measurement>'''


class ProtocolTests(unittest.TestCase):
    def test_fragmented_protocol_and_request(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        requests = []
        errors = []
        def server():
            try:
                conn, _ = listener.accept()
                with conn:
                    conn.settimeout(5)
                    file = conn.makefile('rb')
                    requests.append(file.readline())
                    conn.sendall(b'<hello/><config version="1"></config>')
                    requests.append(file.readline())
                    payload = b'<progress value="100"/><package size="999" /><?xml version="1.0"?>'+XML
                    for i in range(0, len(payload), 7):
                        conn.sendall(payload[i:i+7])
                    file.close()
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        device = Spectis('127.0.0.1', listener.getsockname()[1])
        try:
            device.connect()
            result = device.measure()
            self.assertEqual(result.values, [-0.1, 2.3])
            self.assertEqual(result.info.wavelengths_nm, (400, 500))
            self.assertIn(b'repeat_count="3"', requests[1])
            self.assertIn(b'integration_time="10000000"', requests[1])
            self.assertIn(b'auto="off"', requests[1])
        finally:
            device.close()
            listener.close()
            thread.join(5)
        self.assertFalse(errors)

    def test_invalid_data_rejected(self):
        for data in (XML.replace(b'value="2.3"', b'value="nan"'),
                     XML.replace(b'wavelength="500"', b'wavelength="400"'),
                     XML.replace(b'unit1="mW/m^2/nm"', b'')):
            with self.assertRaises(ValueError):
                parse_measurement(data, 1)

    def test_cancellation(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(InterruptedError):
            Spectis('unused').read_element('measurement', 5, event)


if __name__ == '__main__':
    unittest.main()
