# GL Spectis desktop monitor

Launch **start_monitor.bat**. On first run it creates a private `.venv` environment
and installs the libraries in `requirements.txt`. Later runs reuse that environment;
changed requirements or missing libraries trigger setup again. No administrator
rights are needed, and other Python projects are unaffected.

For a new computer:

1. Install **Python 3.10 or newer** from https://www.python.org/downloads/windows/,
   including the Python launcher, pip and Tcl/Tk (Tkinter).
2. Extract the software into a writable folder (do not run it inside a ZIP).
3. Connect to the instrument's network and double-click **start_monitor.bat**.
   The first setup needs internet access and may take a few minutes.

Python itself is not installed by the launcher. Once setup succeeds, subsequent
launches do not need internet access unless dependencies change or need repair.
If setup fails, the window stays open with the error; correct the problem and retry.
If a private environment becomes damaged, close the app, rename `.venv`, and relaunch.

When sharing the software, include the Python source files, **start_monitor.bat**
and **requirements.txt**. Exclude `.venv`, `__pycache__`, personal captures and
recovery backups; each recipient creates their own environment automatically.
Advanced manual installation remains available with `python -m pip install -r
requirements.txt` followed by `python monitor.py`.

## Connection and collection

Keep the instrument measurement app open and join the same Wi-Fi network.
The app checks the default IP (172.20.10.2) on startup. To change it, edit the
IP in Settings & LSL and click **Connect / check link**. Use **Measure once** or
**Start collecting** after the light turns green. Default: fixed 10-second
exposures × 3 repeats, about 30 seconds plus processing/transfer per spectrum.
Settings apply to direct measurement requests; persistence on the instrument is
not assumed. **Stop collecting** leaves link monitoring enabled. **Disconnect**
closes the instrument connection and stops LSL. An interrupted exposure can still
run on the instrument; let it finish before requesting another.

- Green: instrument traffic or a successful configuration response.
- Yellow: connection/acquisition error, reconnecting, or no response for 10 seconds.
- Red: intentionally disconnected / not yet connected.

The same persistent socket requests configuration every 5 seconds while idle.
During an exposure it reads progress/data; it never opens a competing probe socket.
The display shows the age of the last response. Silence during a long exposure
can mean uncertain connectivity, not necessarily a failed measurement. A bounded
measurement timeout eventually stops collection. Link checks retry after 5 seconds,
but failed collection does not automatically resume or replay measurements.

## Plot, history and color

The dark-blue plot has labelled x/y ticks, major/minor gray grids and physical units.
The panel to its right lists all completed measurements for this app session and
numeric spectral/CIE values for the selection. Click a measurement to browse it
without interrupting collection. **View the last** returns to following new data.

Ctrl/Shift-select multiple measurements to plot the arithmetic mean and shaded
**±1 standard error of the mean (SEM)**. SEM uses sample SD (n−1) divided by √n,
across completed measurements; it is not a confidence interval. A single result
has no SEM. The instrument's internal repeats are not counted as separate samples.
Only measurements with identical device identity, units and wavelength grids can
be combined. **Export selected** writes wavelength, mean/value, SEM and n to CSV.
History is in memory; export needed data before closing.

CIE values are read from the instrument's results: x2, y2, Y2, u2, v2, u2', v2'
and CCT. The swatch is a normalized, gamut-clipped sRGB approximation from xy;
it does not reproduce measured brightness or constitute a calibrated display.
For a multi-selection, XYZ values are averaged first, then converted to xyY.
CCT and other derived indices are not naively averaged. Missing/invalid xyY shows
an unavailable color preview. Single-result CIE values remain available in the table.
Color conversion reference: https://www.w3.org/TR/css-color-4/#color-conversion-code

## Live LSL controls

**Start LSL** and **Stop LSL** work during acquisition, on both tabs. Starting arms
publication from the next new completed measurement. It does not replay the selected
history or its average. Stop closes both outlets immediately; collection continues.

- `GL-Spectis`, type `Spectrum`: one channel per wavelength, instrument units.
- `GL-Spectis-CIE`, type `Colorimetry`: x, y, Y, u, v, u′, v′, CCT in that order.
  Chromaticities are dimensionless; Y uses the device's unit2 metadata; CCT is kelvin.
  Missing CIE fields are sent as NaN, never as zero or invented values.

Both streams use the same host LSL receipt timestamp and irregular sampling rate.
One sample represents one full measurement, not an internal repeat or exposure start.
The outlets first appear after a new measurement arrives; select both in LabRecorder.
Changing device/grid/units stops publishing with an error. If Wi-Fi fails, armed LSL
outlets remain available but no samples are pushed until new collection succeeds.

## Validation

Run `python -m unittest -v` (GUI and local network access are needed).
Tests cover fragmented device replies, acquisition parameters, cancellation,
heartbeat/reconnection behavior, spectrum validation, CIE parsing, mean/SEM,
color conversion, LSL start/stop and matched timestamps, plus history navigation
while new measurements arrive. `python preview_monitor.py` shows a clearly labelled
offline synthetic preview without connecting to the instrument or streaming data.

The desktop was visually checked at this computer's display size. A previous live
capture verified 256 spectral channels and CIE results from firmware 3.0.51 on
Spectis Touch 18H00142. The new three-repeat acquisition and continuous heartbeat
have not yet been validated on hardware because the Wi-Fi link has been intermittent.
No calibration adjustments are performed.

## Files

- `monitor.py`: Tkinter GUI and plotting.
- `acquisition.py`: serial worker for connection, heartbeat and acquisition.
- `spectis.py`: device protocol and XML parsing.
- `streaming.py`, `bridge.py`: synchronized CIE/spectrum LSL and older synthetic demo.
- `analysis_tools.py`: statistics and screen-color conversion.
- `probe_wifi.py`, `probe_usb.py`: connection diagnostics.

Historical recovery notes and backups remain in RECOVERY.md, USB_FINDINGS.md,
and recovery_backup/. Vendor binaries, backups and captures remain ignored by Git.
