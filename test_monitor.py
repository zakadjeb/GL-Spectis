import time
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
from measurement_csv import load_measurements
from monitor import Monitor
from test_features import sample


class MonitorTests(unittest.TestCase):
    def test_settings_file_save_load_and_startup(self):
        with tempfile.TemporaryDirectory(prefix='spectis settings ') as folder:
            path = Path(folder) / 'settings.txt'
            app = Monitor(auto_connect=False, config_path=path)
            app.withdraw()
            try:
                app.host.set('192.168.1.50')
                app.exposure.set('5')
                app.repeats.set('2')
                app.plot_mode.set('overlay')
                app.fixed_y.set(True)
                app.y_max.set('50')
                app.background_color.set('#ffffff')
                app.palette[2].set('#123456')
                app.save_settings()
                saved = path.read_text()
                app.host.set('other')
                app.background_color.set('#000000')
                app.load_settings()
                self.assertEqual(app.host.get(), '192.168.1.50')
                self.assertEqual(app.background_color.get(), '#ffffff')
                self.assertEqual(app.plot_options['ylim'], (0, 50))
                self.assertEqual(app.plot_options['palette'][2], '#123456')
                self.assertFalse(app.publisher.enabled)
                self.assertIsNone(app.requested_host)
                app.y_max.set('nan')
                with patch('monitor.messagebox.showerror') as error:
                    app.save_settings()
                    error.assert_called_once()
                self.assertEqual(path.read_text(), saved)
                path.write_text('{broken')
                with patch('monitor.messagebox.showerror') as error:
                    app.load_settings()
                    error.assert_called_once()
                self.assertEqual(app.plot_options['ylim'], (0, 50))
                path.write_text(saved)
            finally:
                app.worker.shutdown.set()
                app.worker.join(3)
                for callback in app.tk.call('after', 'info'):
                    app.tk.call('after', 'cancel', callback)
                app.destroy()
            restored = Monitor(auto_connect=False, config_path=path)
            restored.withdraw()
            try:
                self.assertEqual(restored.host.get(), '192.168.1.50')
                self.assertEqual(restored.plot_options['mode'], 'overlay')
                self.assertEqual(restored.axes.get_ylim(), (0, 50))
                self.assertEqual(restored.exposure.get(), '5.0')
                self.assertEqual(restored.repeats.get(), '2')
            finally:
                restored.worker.shutdown.set()
                restored.worker.join(3)
                for callback in restored.tk.call('after', 'info'):
                    restored.tk.call('after', 'cancel', callback)
                restored.destroy()

    def test_visualization_limits_colors_and_overlay(self):
        app = Monitor(auto_connect=False)
        app.withdraw()
        try:
            app.add_measurement(sample([1, 2]))
            app.add_measurement(sample([3, 6]))
            app.pause_follow()
            app.history_tree.selection_set('0', '1')
            app.plot_mode.set('overlay')
            app.fixed_y.set(True)
            app.y_min.set('-1')
            app.y_max.set('4')
            app.background_color.set('#ffffff')
            app.palette[0].set('#aa0000')
            app.palette[1].set('#0000aa')
            app.apply_visualization()
            self.assertEqual(app.axes.get_ylim(), (-1, 4))
            self.assertEqual(app.axes.get_facecolor(), (1, 1, 1, 1))
            self.assertEqual(app.plot_foreground, '#152030')
            self.assertEqual([list(line.get_ydata()) for line in app.axes.lines], [[1, 2], [3, 6]])
            self.assertEqual([line.get_color() for line in app.axes.lines], ['#aa0000', '#0000aa'])
            self.assertEqual([line.get_label() for line in app.axes.lines], ['Trial 1', 'Trial 2'])
            self.assertEqual(len(app.axes.collections), 0)
            app.view_latest()
            app.add_measurement(sample([10, 20]))
            self.assertEqual(app.axes.get_ylim(), (-1, 4))
            self.assertEqual(app.history[-1].values, [10, 20])
            app.y_max.set('nan')
            with patch('monitor.messagebox.showerror') as error:
                app.apply_visualization()
                error.assert_called_once()
            self.assertEqual(app.plot_options['ylim'], (-1, 4))
            app.fixed_y.set(False)
            app.plot_mode.set('mean')
            app.mean_color.set('#aa00aa')
            app.pause_follow()
            app.history_tree.selection_set('0', '1')
            app.apply_visualization()
            self.assertEqual(len(app.axes.lines), 1)
            self.assertEqual(list(app.axes.lines[0].get_ydata()), [2, 4])
            self.assertEqual(app.axes.lines[0].get_color(), '#aa00aa')
            self.assertEqual(len(app.axes.collections), 1)
            self.assertGreater(app.axes.get_ylim()[1], 4)
            app.clear_measurements()
            self.assertEqual(app.axes.get_facecolor(), (1, 1, 1, 1))
        finally:
            app.worker.shutdown.set()
            app.worker.join(3)
            for callback in app.tk.call('after', 'info'):
                app.tk.call('after', 'cancel', callback)
            app.destroy()

    def test_remove_and_clear_while_collecting(self):
        app = Monitor(auto_connect=False)
        app.withdraw()
        try:
            for value in (1, 2, 3, 4):
                app.add_measurement(sample([value, value]))
            app.add_measurement(sample([8, 8]), imported=True)
            app.pause_follow()
            app.history_tree.selection_set('1', '3')
            app.set_busy(True)
            app.start_lsl()
            app.remove_selected()
            app.update()
            self.assertEqual([m.values[0] for m in app.history], [1, 3, 8])
            self.assertEqual(app.history_tree.get_children(), ('0', '1', '2'))
            self.assertEqual(app.selected()[0].values, [3, 3])
            self.assertEqual(list(app.axes.lines[0].get_ydata()), [3, 3])
            self.assertIs(app.latest, app.history[1])
            app.view_latest()
            self.assertEqual(app.history_tree.selection(), ('1',))
            app.clear_measurements()
            app.update()
            self.assertEqual(app.history, [])
            self.assertIsNone(app.latest)
            self.assertEqual(app.history_tree.get_children(), ())
            self.assertEqual(app.values_tree.get_children(), ())
            self.assertEqual(app.cie_tree.get_children(), ())
            self.assertEqual(len(app.axes.lines), 0)
            self.assertEqual(app.swatch.cget('text'), 'N/A')
            self.assertTrue(app.busy)
            self.assertTrue(app.publisher.enabled)
            self.assertFalse(app.worker.cancel.is_set())
            app.clear_measurements()  # Empty history and selection are harmless.
            app.remove_selected()
            app.add_measurement(sample([9, 10]))
            app.update()
            self.assertEqual(app.history_tree.selection(), ('0',))
            self.assertEqual(app.selected()[0].values, [9, 10])
            app.remove_selected()  # Removing the last trial resets the preview too.
            app.update()
            self.assertFalse(app.history)
            self.assertEqual(len(app.axes.lines), 0)
        finally:
            app.publisher.stop()
            app.worker.shutdown.set()
            app.worker.join(3)
            for callback in app.tk.call('after', 'info'):
                app.tk.call('after', 'cancel', callback)
            app.destroy()

    def test_export_and_open_keep_individual_trials_without_lsl_replay(self):
        app = Monitor(auto_connect=False)
        app.withdraw()
        try:
            app.add_measurement(sample([1, 2]))
            app.add_measurement(sample([3, 6]))
            app.add_measurement(sample([9, 10]))
            app.pause_follow()
            app.history_tree.selection_set('0', '2')
            with tempfile.TemporaryDirectory(prefix='spectis gui csv ') as folder:
                path = str(Path(folder) / 'selected.csv')
                with patch('monitor.filedialog.asksaveasfilename', return_value=path):
                    app.export()
                saved = load_measurements(path)
                self.assertEqual([m.values for m in saved], [[1, 2], [9, 10]])
                app.start_lsl()
                with patch.object(app.publisher, 'publish') as publish, patch('monitor.filedialog.askopenfilename', return_value=path):
                    app.open_csv()
                    publish.assert_not_called()
                self.assertEqual(len(app.history), 5)
                self.assertEqual(app.history_tree.selection(), ('3', '4'))
                self.assertFalse(app.follow_latest)
                self.assertEqual(list(app.axes.lines[0].get_ydata()), [5, 6])
                app.view_latest()
                self.assertEqual(app.history_tree.selection(), ('2',))
                app.pause_follow()
                app.history_tree.selection_set('3')
                app.add_measurement(sample([11, 12]))
                self.assertEqual(app.history_tree.selection(), ('3',))
                # Failed import is atomic: even valid preceding trials are not added.
                Path(path).write_text('invalid,csv\n')
                with patch('monitor.filedialog.askopenfilename', return_value=path), patch('monitor.messagebox.showerror') as error:
                    app.open_csv()
                    error.assert_called_once()
                self.assertEqual(len(app.history), 6)
        finally:
            app.publisher.stop()
            app.worker.shutdown.set()
            app.worker.join(3)
            for callback in app.tk.call('after', 'info'):
                app.tk.call('after', 'cancel', callback)
            app.destroy()

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
            self.assertEqual(len(app.axes.child_axes), 1)
            self.assertEqual(app.axes.child_axes[0].get_xlim(), app.axes.get_xlim())
            self.assertEqual(list(app.axes.lines[0].get_ydata()), [2,4])
            app.add_measurement(sample([5,10]))
            app.update()
            self.assertEqual(app.history_tree.selection(), ('0','1'))
            self.assertFalse(app.publisher.enabled)
            app.view_latest()
            app.update()
            self.assertEqual(app.history_tree.selection(), ('2',))
            self.assertEqual(len(app.axes.collections), 0)
            self.assertEqual(len(app.axes.child_axes), 1)
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
            for callback in app.tk.call('after', 'info'):
                app.tk.call('after', 'cancel', callback)
            app.destroy()


if __name__ == '__main__':
    unittest.main()
