import time
import unittest
from monitor import Monitor
from test_features import sample


class MonitorTests(unittest.TestCase):
    def test_history_does_not_follow_until_requested(self):
        app = Monitor(auto_connect=False)
        app.withdraw()
        try:
            app.add_measurement(sample([1,2]))
            app.add_measurement(sample([3,6]))
            app.pause_follow()
            app.history_tree.selection_set('0', '1')
            app.history_selected()
            app.update()
            self.assertEqual(len(app.axes.collections), 1)
            self.assertEqual(list(app.axes.lines[0].get_ydata()), [2,4])
            app.add_measurement(sample([5,10]))
            app.update()
            self.assertEqual(app.history_tree.selection(), ('0','1'))
            self.assertFalse(app.publisher.enabled)
            app.view_latest()
            app.update()
            self.assertEqual(app.history_tree.selection(), ('2',))
            self.assertEqual(len(app.axes.collections), 0)
            self.assertEqual(len(app.values_tree.get_children()), 2)
            self.assertEqual(len(app.cie_tree.get_children()), 8)
            app.start_lsl()
            self.assertTrue(app.publisher.enabled)
            app.stop_lsl()
            self.assertFalse(app.publisher.enabled)
            app.events.put(('activity', time.monotonic()-11))
            app.poll()
            self.assertEqual(app.link_color, 'yellow')
            app.disconnect()
            self.assertEqual(app.link_color, 'red')
        finally:
            app.worker.shutdown.set()
            app.worker.join(3)
            app.destroy()


if __name__ == '__main__':
    unittest.main()
