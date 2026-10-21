"""Run with: python -m unittest -v"""

import unittest

import pylsl

from bridge import DemoDevice, make_outlet, validate_info, validate_spectrum, DeviceInfo


class BridgeTests(unittest.TestCase):
    def test_rejects_invalid_measurements(self):
        for values in ([1], [1, float("nan")], [1, float("inf")]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_spectrum(values, 2)

    def test_rejects_ambiguous_wavelengths(self):
        for grid in ((), (500, 500), (600, 500), (float("nan"),)):
            with self.subTest(grid=grid), self.assertRaises(ValueError):
                validate_info(DeviceInfo("test", "test", grid, "a.u."))

    def test_lsl_round_trip(self):
        with DemoDevice() as device:
            outlet = make_outlet(device.info, True, pylsl)
            streams = pylsl.resolve_byprop("source_id", outlet.get_info().source_id(), timeout=5)
            self.assertTrue(streams, "LSL stream discovery timed out")
            inlet = pylsl.StreamInlet(streams[0])
            try:
                inlet.open_stream(timeout=5)
                self.assertTrue(outlet.wait_for_consumers(5))
                metadata = inlet.info(timeout=5)
                self.assertEqual(metadata.name(), "GL-Spectis-DEMO")
                self.assertEqual(metadata.channel_count(), 81)
                self.assertEqual(metadata.desc().child_value("simulated"), "true")
                sample = device.read_spectrum()
                sent_at = pylsl.local_clock()
                outlet.push_sample(sample, sent_at)
                received, timestamp = inlet.pull_sample(timeout=5)
                self.assertEqual(received, sample)
                self.assertAlmostEqual(timestamp, sent_at, places=6)
            finally:
                inlet.close_stream()


if __name__ == "__main__":
    unittest.main()
