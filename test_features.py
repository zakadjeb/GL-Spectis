import math
import queue
import time
import unittest
from dataclasses import replace
from unittest.mock import patch
import numpy as np
from analysis_tools import summarize, selection_xyY, xy_to_hex, CIE_CHANNELS
from acquisition import Acquisition
from spectis import parse_measurement
from streaming import Publisher
from test_spectis import XML


def sample(values=None):
    results = b'''<results><parameter name="x2">0.3127</parameter>
    <parameter name="y2">0.3290</parameter><parameter name="Y2">100</parameter>
    <parameter name="u2">0.1978</parameter><parameter name="v2">0.3122</parameter>
    <parameter name="u2'">0.1978</parameter><parameter name="v2'">0.4683</parameter>
    <parameter name="CCT">6500</parameter></results>'''
    raw = XML.replace(b'</measurement>', results+b'</measurement>')
    raw = raw.replace(b'unit1="mW/m^2/nm"', b'unit1="mW/m^2/nm" unit2="lx"')
    m = parse_measurement(raw, 100)
    return replace(m, values=values) if values is not None else m


class AnalysisTests(unittest.TestCase):
    def test_cie_parser(self):
        m = sample()
        self.assertEqual(m.results['CCT'], 6500)
        self.assertEqual(m.results["v2'"], .4683)
        self.assertEqual(m.y_unit, 'lx')

    def test_sample_sem(self):
        _, mean, sem = summarize([sample([1, 2]), sample([3, 6]), sample([5, 10])])
        np.testing.assert_allclose(mean, [3, 6])
        np.testing.assert_allclose(sem, [2/math.sqrt(3), 4/math.sqrt(3)])
        self.assertIsNone(summarize([sample()])[2])
        with self.assertRaises(ValueError):
            summarize([sample(), replace(sample(), info=replace(sample().info, unit='other'))])

    def test_color_and_weighted_xyz(self):
        self.assertEqual(xy_to_hex(.3127, .329), '#ffffff')
        self.assertIsNone(xy_to_hex(.4, 0))
        a = sample()
        b = replace(a, results={'x2':.4, 'y2':.4, 'Y2':200})
        x, y, Y = selection_xyY([a,b])
        self.assertEqual(Y, 150)
        self.assertNotAlmostEqual(x, (.3127+.4)/2, places=5)
        self.assertIsNone(selection_xyY([replace(a, results={})]))

    def test_lsl_toggle_and_no_replay(self):
        import pylsl
        publisher = Publisher()
        with patch('pylsl.local_clock', return_value=100):
            publisher.start()
        self.assertFalse(publisher.publish(replace(sample(), received_at=99)))
        with patch('streaming.make_outlet') as spectral, patch('pylsl.StreamOutlet') as cie:
            m = replace(sample(), received_at=101)
            self.assertTrue(publisher.publish(m))
            spectral.return_value.push_sample.assert_called_once_with(m.values, 101)
            cie.return_value.push_sample.assert_called_once_with(
                [m.results[k] for k, _, _ in CIE_CHANNELS], 101)
            publisher.stop()
            self.assertFalse(publisher.publish(replace(m, received_at=102)))
        self.assertIsNone(publisher.spectrum)

    def test_cie_lsl_round_trip(self):
        import pylsl
        publisher = Publisher()
        publisher.start()
        m = replace(sample(), received_at=pylsl.local_clock())
        publisher.publish(m)
        streams = pylsl.resolve_byprop('name', 'GL-Spectis-CIE', timeout=5)
        self.assertTrue(streams)
        inlet = pylsl.StreamInlet(streams[0])
        try:
            inlet.open_stream(timeout=5)
            self.assertTrue(publisher.cie.wait_for_consumers(5))
            m = replace(m, received_at=pylsl.local_clock())
            publisher.publish(m)
            values, timestamp = inlet.pull_sample(timeout=5)
            self.assertEqual(values, [m.results[k] for k, _, _ in CIE_CHANNELS])
            self.assertAlmostEqual(timestamp, m.received_at, places=6)
            self.assertEqual(inlet.info().channel_count(), 8)
        finally:
            inlet.close_stream()
            publisher.stop()


class WorkerTests(unittest.TestCase):
    def test_measurement_not_retried_after_connection_failure(self):
        counts = {'connect':0, 'measure':0}
        class Device:
            def __init__(self, host, on_activity):
                pass
            def connect(self):
                counts['connect'] += 1
            def check(self, cancel):
                pass
            def measure(self, *args):
                counts['measure'] += 1
                raise ConnectionError('Simulated dropped Wi-Fi')
            def close(self):
                pass
        worker = Acquisition(queue.Queue(), Device, check_interval=.05, retry_interval=.05)
        worker.start()
        try:
            worker.commands.put(('connect', 'test'))
            worker.commands.put(('start', ('continuous', 10, 3)))
            deadline = time.monotonic()+3
            while counts['connect'] < 2 and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertGreaterEqual(counts['connect'], 2)
            self.assertEqual(counts['measure'], 1)
        finally:
            worker.shutdown.set()
            worker.join(3)

    def test_idle_heartbeat_and_one_connection(self):
        counts = {'connect':0, 'check':0, 'close':0, 'measure':0}
        class Device:
            def __init__(self, host, on_activity):
                self.activity = on_activity
            def connect(self):
                counts['connect'] += 1
            def check(self, cancel):
                counts['check'] += 1
                self.activity(time.monotonic())
            def measure(self, *args):
                counts['measure'] += 1
                return sample()
            def close(self):
                counts['close'] += 1
        events = queue.Queue()
        worker = Acquisition(events, Device, check_interval=.05)
        worker.start()
        try:
            worker.commands.put(('connect', 'test'))
            deadline = time.monotonic()+3
            while counts['check'] < 2 and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertGreaterEqual(counts['check'], 2)
            worker.commands.put(('start', ('once', 10, 3)))
            deadline = time.monotonic()+3
            while counts['measure'] < 1 and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertEqual(counts['measure'], 1)
            self.assertEqual(counts['connect'], 1)
        finally:
            worker.shutdown.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(counts['close'], 1)


if __name__ == '__main__':
    unittest.main()
