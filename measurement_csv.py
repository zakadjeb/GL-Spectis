"""Versioned long-form CSV: one row per wavelength, contiguous blocks per trial."""
import csv
from datetime import datetime, timezone
import json
import math

from analysis_tools import CIE_CHANNELS, xy_to_hex
from bridge import DeviceInfo, validate_info, validate_spectrum
from spectis import Measurement


FIELDS = ['format_version', 'trial_id', 'channel_count', 'lsl_timestamp_s',
          'received_unix_s', 'received_utc', 'clock_session', 'model', 'serial',
          'spectral_unit', 'Y_unit', 'illuminance_lux',
          *[label for _, label, _ in CIE_CHANNELS], 'color_hex_srgb',
          'results_json', 'status_json', 'wavelength_nm', 'spectral_value']


def finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Numeric values must be finite')
    return number


def utc_text(unix):
    return '' if unix is None else datetime.fromtimestamp(unix, timezone.utc).isoformat()


def metadata(m, trial_id):
    validate_info(m.info)
    validate_spectrum(m.values, len(m.info.wavelengths_nm))
    color = xy_to_hex(m.results.get('x2', math.nan), m.results.get('y2', math.nan))
    return dict(format_version='1', trial_id=str(trial_id), channel_count=len(m.values),
                lsl_timestamp_s=finite(m.received_at),
                received_unix_s='' if m.received_unix is None else finite(m.received_unix),
                received_utc=utc_text(m.received_unix), clock_session=m.clock_session,
                model=m.info.model, serial=m.info.serial, spectral_unit=m.info.unit,
                Y_unit=m.y_unit,
                illuminance_lux=m.results.get('Y2', '') if m.y_unit.lower() in ('lx', 'lux') else '',
                **{label: m.results.get(key, '') for key, label, _ in CIE_CHANNELS},
                color_hex_srgb=color or '',
                results_json=json.dumps(m.results, allow_nan=False, sort_keys=True),
                status_json=json.dumps(m.status, allow_nan=False, sort_keys=True))


def save_measurements(path, measurements):
    if not measurements:
        raise ValueError('Select at least one measurement')
    # Validate every trial before touching the destination file.
    headers = [metadata(m, i+1) for i, m in enumerate(measurements)]
    with open(path, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for m, header in zip(measurements, headers):
            for wavelength, value in zip(m.info.wavelengths_nm, m.values):
                writer.writerow(dict(header, wavelength_nm=wavelength, spectral_value=value))


def load_measurements(path):
    """Validate the complete file before returning anything to the GUI."""
    groups = {}
    with open(path, newline='', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file, strict=True)
        if reader.fieldnames != FIELDS:
            raise ValueError('This is not a trial CSV from this monitor. Older mean/SEM exports '
                             'do not contain the original trials or timestamps and cannot restore them.')
        for line, row in enumerate(reader, 2):
            try:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError('Wrong number of columns')
                if row['format_version'] != '1' or not row['trial_id']:
                    raise ValueError('Unsupported format or missing trial ID')
                wavelength, value = finite(row['wavelength_nm']), finite(row['spectral_value'])
                header = {k: row[k] for k in FIELDS[:-2]}
                trial = groups.setdefault(row['trial_id'], (header, [], []))
                if trial[0] != header:
                    raise ValueError('Metadata differs within a trial')
                trial[1].append(wavelength)
                trial[2].append(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f'CSV row {line}: {exc}') from exc
    measurements = []
    for trial_id, (row, wavelengths, values) in groups.items():
        try:
            if int(row['channel_count']) != len(values):
                raise ValueError('Missing or extra spectral rows')
            info = DeviceInfo(row['model'], row['serial'], tuple(wavelengths), row['spectral_unit'])
            validate_info(info)
            validate_spectrum(values, len(wavelengths))
            results, status = json.loads(row['results_json']), json.loads(row['status_json'])
            if not isinstance(results, dict) or not isinstance(status, dict):
                raise ValueError('Results and status must be objects')
            results = {key: finite(value) for key, value in results.items()}
            unix = finite(row['received_unix_s']) if row['received_unix_s'] else None
            m = Measurement(info, values, status, b'', finite(row['lsl_timestamp_s']),
                            results, row['Y_unit'], unix, row['clock_session'])
            expected = metadata(m, trial_id)
            # Reject conflicting duplicate color/time fields instead of silently ignoring edits.
            for key in ['illuminance_lux', *[label for _, label, _ in CIE_CHANNELS]]:
                if (row[key] == '') != (expected[key] == ''):
                    raise ValueError(f'Inconsistent {key}')
                if row[key] and finite(row[key]) != float(expected[key]):
                    raise ValueError(f'Inconsistent {key}')
            if row['color_hex_srgb'] != expected['color_hex_srgb'] or row['received_utc'] != expected['received_utc']:
                raise ValueError('Inconsistent color or UTC timestamp')
            measurements.append(m)
        except (ValueError, TypeError, OverflowError, OSError) as exc:
            raise ValueError(f'Trial {trial_id}: {exc}') from exc
    if not measurements:
        raise ValueError('The CSV contains no trials')
    return measurements
