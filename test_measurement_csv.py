import csv
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from measurement_csv import save_measurements, load_measurements
from test_features import sample


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='spectis csv ')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'trials.csv'

    def rows(self):
        with self.path.open(newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))

    def rewrite(self, rows):
        with self.path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def test_all_trials_exact_round_trip_with_times_and_color(self):
        a = replace(sample([1.23456789012345, 2]), received_at=98765.123456789,
                    received_unix=1793100000.123456, clock_session='session-a',
                    status={'integration time': '10000000', 'note': 'comma, newline\nand "quotes"'})
        b = replace(a, values=[3, 8], received_at=98795.987654321,
                    received_unix=1793100030.987654)
        save_measurements(self.path, [a, b])
        rows = self.rows()
        self.assertEqual([r['trial_id'] for r in rows], ['1', '1', '2', '2'])
        self.assertEqual(float(rows[2]['spectral_value']), 3)
        self.assertEqual(float(rows[0]['illuminance_lux']), 100)
        self.assertEqual(rows[0]['color_hex_srgb'], '#ffffff')
        self.assertTrue(rows[0]['received_utc'].endswith('+00:00'))
        loaded = load_measurements(self.path)
        self.assertEqual(loaded, [replace(a, xml=b''), replace(b, xml=b'')])
        # A reopened file can be saved again without losing original times.
        save_measurements(self.path, loaded)
        self.assertEqual(load_measurements(self.path), loaded)
        for before, after in zip(rows, self.rows()):
            for key in ('lsl_timestamp_s', 'received_unix_s', 'received_utc', 'clock_session'):
                self.assertEqual(before[key], after[key])

    def test_mixed_grids_missing_color_and_non_lux_units(self):
        a = replace(sample(), y_unit='cd/m2', received_unix=None)
        b = replace(a, info=replace(a.info, wavelengths_nm=(400., 500., 600.)),
                    values=[1, 2, 3], results={})
        save_measurements(self.path, [a, b])
        rows = self.rows()
        self.assertEqual(rows[0]['illuminance_lux'], '')
        self.assertEqual(rows[0]['received_utc'], '')
        self.assertEqual(rows[-1]['color_hex_srgb'], '')
        self.assertEqual(load_measurements(self.path), [replace(a, xml=b''), replace(b, xml=b'')])

    def test_reject_truncated_duplicate_conflicting_and_invalid_rows(self):
        for corruption in ('truncated', 'duplicate', 'metadata', 'numeric', 'color'):
            with self.subTest(corruption=corruption):
                save_measurements(self.path, [sample()])
                rows = self.rows()
                if corruption == 'truncated':
                    rows.pop()
                elif corruption == 'duplicate':
                    rows[1]['wavelength_nm'] = rows[0]['wavelength_nm']
                elif corruption == 'metadata':
                    rows[1]['lsl_timestamp_s'] = '900'
                elif corruption == 'numeric':
                    rows[0]['spectral_value'] = 'nan'
                else:
                    for row in rows:
                        row['illuminance_lux'] = '999'
                self.rewrite(rows)
                with self.assertRaises(ValueError):
                    load_measurements(self.path)

    def test_old_averaged_export_has_clear_error(self):
        self.path.write_text('wavelength_nm,mean_x,SEM_x,n\n400,1,0,3\n')
        with self.assertRaisesRegex(ValueError, 'original trials'):
            load_measurements(self.path)


if __name__ == '__main__':
    unittest.main()
