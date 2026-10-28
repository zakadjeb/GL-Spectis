"""Human-readable settings.txt (JSON), validated before applying or replacing it."""
import json
import math
from pathlib import Path
import re
import tempfile


def validate_settings(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Settings must be a JSON object with version 1.')
    required = {'version', 'host', 'exposure_seconds', 'repeats', 'plot_mode',
                'fixed_y', 'y_min', 'y_max', 'background_color', 'mean_color', 'overlay_colors'}
    if set(data) != required:
        raise ValueError('Settings file has missing or unknown fields.')
    if not isinstance(data['host'], str) or not data['host'].strip():
        raise ValueError('Enter an instrument IP address or hostname.')
    for key in ('exposure_seconds', 'y_min', 'y_max'):
        if type(data[key]) not in (float, int) or not math.isfinite(data[key]):
            raise ValueError(f'{key} must be a finite number.')
    if not .0026 <= data['exposure_seconds'] <= 200:
        raise ValueError('Exposure must be 0.0026–200 seconds.')
    if type(data['repeats']) is not int or not 1 <= data['repeats'] <= 250:
        raise ValueError('Repeats must be a whole number from 1 to 250.')
    if data['plot_mode'] not in ('mean', 'overlay') or type(data['fixed_y']) is not bool:
        raise ValueError('Use plot_mode mean/overlay and fixed_y true/false.')
    if data['y_min'] >= data['y_max']:
        raise ValueError('The y-axis minimum must be below the maximum.')
    palette = data['overlay_colors']
    if not isinstance(palette, list) or len(palette) != 6:
        raise ValueError('Provide six overlay colors.')
    for color in [data['background_color'], data['mean_color'], *palette]:
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError('Colors must use six-digit hex codes, such as #101b2c.')
    return data


def read_settings(path):
    return validate_settings(json.loads(Path(path).read_text(encoding='utf-8-sig')))


def write_settings(path, data):
    data = validate_settings(data)
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name+'.', suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            file.write(json.dumps(data, indent=2, allow_nan=False)+'\n')
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
