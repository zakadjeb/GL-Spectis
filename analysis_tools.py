"""Spectrum summaries and approximate color previews; no instrument mutations."""
import math
import numpy as np

CIE_CHANNELS = [('x2', 'CIE1931_x', 'dimensionless'),
                ('y2', 'CIE1931_y', 'dimensionless'),
                ('Y2', 'CIE1931_Y', None),
                ('u2', 'CIE1960_u', 'dimensionless'),
                ('v2', 'CIE1960_v', 'dimensionless'),
                ("u2'", 'CIE1976_u_prime', 'dimensionless'),
                ("v2'", 'CIE1976_v_prime', 'dimensionless'),
                ('CCT', 'CCT', 'K')]


def summarize(measurements):
    if not measurements:
        raise ValueError('Select at least one measurement')
    info = measurements[0].info
    if any(m.info != info for m in measurements):
        raise ValueError('Select measurements with the same device, wavelength grid and units')
    data = np.asarray([m.values for m in measurements], dtype=float)
    mean = data.mean(axis=0)
    sem = data.std(axis=0, ddof=1)/math.sqrt(len(data)) if len(data) > 1 else None
    return info, mean, sem


def xy_to_hex(x, y):
    if not all(math.isfinite(v) for v in (x, y)) or x < 0 or y <= 0 or x+y > 1:
        return None
    # XYZ -> linear sRGB matrix and transfer function: W3C CSS Color 4, section 19.
    xyz = np.array([x/y, 1.0, (1-x-y)/y])
    rgb = np.array([[12831/3959, -329/214, -1974/3959],
                    [-851781/878810, 1648619/878810, 36519/878810],
                    [705/12673, -2585/12673, 705/667]]) @ xyz
    # Normalize brightness and clip out-of-gamut channels for a screen preview only.
    rgb = np.maximum(rgb, 0)
    if max(rgb) <= 0:
        return None
    rgb /= max(rgb)
    rgb = np.where(rgb <= .0031308, 12.92*rgb, 1.055*rgb**(1/2.4)-.055)
    return '#' + ''.join(f'{round(float(v)*255):02x}' for v in rgb)


def selection_xyY(measurements):
    """Average tristimulus values, not chromaticities, for a multi-spectrum preview."""
    xyz = []
    if len({m.y_unit for m in measurements}) != 1:
        return None
    for m in measurements:
        x, y, Y = (m.results.get(k, math.nan) for k in ('x2', 'y2', 'Y2'))
        if not all(math.isfinite(v) for v in (x,y,Y)) or y <= 0 or x < 0 or x+y > 1 or Y <= 0:
            return None
        xyz.append((x*Y/y, Y, (1-x-y)*Y/y))
    if not xyz:
        return None
    X, Y, Z = np.mean(xyz, axis=0)
    return X/(X+Y+Z), Y/(X+Y+Z), Y
