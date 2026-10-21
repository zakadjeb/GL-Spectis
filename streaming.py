"""Independent LSL start/stop; called only on the GUI thread."""
import math
from analysis_tools import CIE_CHANNELS
from bridge import make_outlet


class Publisher:
    def __init__(self):
        self.enabled = False
        self.spectrum = self.cie = None
        self.identity = None
        self.count = 0

    def start(self):
        import pylsl
        self.stop()
        self.enabled = True
        self.armed_at = pylsl.local_clock()
        self.count = 0

    def stop(self):
        self.enabled = False
        self.spectrum = self.cie = None
        self.identity = None

    def publish(self, measurement):
        if not self.enabled or measurement.received_at < self.armed_at:
            return False
        import pylsl
        identity = (measurement.info, measurement.y_unit)
        if self.identity is not None and identity != self.identity:
            self.stop()
            raise ValueError('Device, wavelength grid or units changed; restart LSL')
        if self.spectrum is None:
            self.spectrum = make_outlet(measurement.info, False, pylsl)
            info = pylsl.StreamInfo('GL-Spectis-CIE', 'Colorimetry', len(CIE_CHANNELS),
                                   pylsl.IRREGULAR_RATE, 'double64',
                                   f'gl-spectis:{measurement.info.model}:{measurement.info.serial}:cie')
            desc = info.desc()
            desc.append_child_value('serial_number', measurement.info.serial)
            desc.append_child_value('timestamp_source', 'host_lsl_clock_after_read')
            desc.append_child_value('missing_values', 'NaN means unavailable in device results')
            desc.append_child_value('source', 'Instrument results; not display RGB or selected-history average')
            channels = desc.append_child('channels')
            for key, label, unit in CIE_CHANNELS:
                ch = channels.append_child('channel')
                ch.append_child_value('label', label)
                ch.append_child_value('unit', unit or measurement.y_unit)
                ch.append_child_value('device_result_key', key)
            self.cie = pylsl.StreamOutlet(info)
            self.identity = identity
        self.spectrum.push_sample(measurement.values, measurement.received_at)
        self.cie.push_sample([measurement.results.get(k, math.nan) for k, _, _ in CIE_CHANNELS],
                             measurement.received_at)
        self.count += 1
        return True
