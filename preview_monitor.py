"""Offline UI preview only: synthetic history, no instrument connection or LSL."""
from dataclasses import replace
import math
from bridge import DeviceInfo
from spectis import Measurement
from monitor import Monitor

app = Monitor(auto_connect=False)
app.title('GL Spectis | OFFLINE synthetic UI preview')
wavelengths = tuple(range(340, 781, 5))
info = DeviceInfo('SYNTHETIC PREVIEW', 'preview-only', wavelengths, 'a.u.')
for i in range(4):
    values = [(1+i*.08)*(math.exp(-((w-455)/18)**2)+.65*math.exp(-((w-570)/65)**2))
              for w in wavelengths]
    m = Measurement(info, values, {'battery level':'N/A'}, b'', 0,
                    {'x2':.3127,'y2':.329,'Y2':100+i*10,
                     'u2':.1978,'v2':.3122,"u2'":.1978,"v2'":.4683,'CCT':6500}, 'a.u.')
    app.add_measurement(m)
app.pause_follow()
app.history_tree.selection_set('0','1','2','3')
app.history_selected()
app.add_log('OFFLINE PREVIEW: all spectra and CIE values are synthetic')
app.mainloop()
