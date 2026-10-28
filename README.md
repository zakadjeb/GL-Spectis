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
A compact color strip below the x-axis aligns approximate visible colors with the
wavelength scale. Gray marks wavelengths outside the displayed visible range
(380–780 nm). This is an orientation guide, not a calibrated color rendering.
The panel to its right lists all completed measurements for this app session and
numeric spectral/CIE values for the selection. Click a measurement to browse it
without interrupting collection. **View the last** returns to following new data.

Ctrl/Shift-select multiple measurements to plot the arithmetic mean and shaded
**±1 standard error of the mean (SEM)**. SEM uses sample SD (n−1) divided by √n,
across completed measurements; it is not a confidence interval. A single result
has no SEM. The instrument's internal repeats are not counted as separate samples.
Only measurements with identical device identity, units and wavelength grids can
be combined in the preview. **Export selected** saves each selected trial separately,
even when the plot shows their mean. Trials are concatenated vertically: one row
per wavelength, with a trial ID and repeated trial metadata. Different wavelength
grids/devices can be exported together, but cannot be averaged together.
History is in memory; export needed data before closing.

**Remove selected** removes the highlighted trials from the current history.
**Clear all** empties the history, plot and color preview. Export anything you want
to keep first. These controls do not delete saved CSV files or stop acquisition or
LSL. After clearing, the next completed measurement appears automatically.

## Saving and reopening trials

The **Visualization** tab controls how selected spectra appear. Choose **Mean spectrum
with ±1 standard error** or **Individual spectra overlaid**, then click **Apply
visualization**. Overlay legends identify trial numbers in the history; the values
table and color preview still summarize the selection. Select compatible measurements
with Ctrl/Shift to compare them.

Enable **Fix the y-axis range** and enter a minimum and maximum in the displayed
spectral units to retain the same scale across measurements. Values outside the
range are clipped on screen only. Uncheck it and apply to restore automatic scaling.
Color buttons change the plot background, mean line/SEM shading, and six overlay
line colors (cycled by trial number). Axis text and grids adapt to the background.
These settings do not change CSV or LSL data.

Use **Save settings** in Visualization or Settings & LSL to save the current
connection IP, exposure, repeats, plot mode, y-axis limits and colors to
**settings.txt** beside the launcher. Saving also applies the visualization edits.
**Load settings** restores the file; stop collection first, and click **Connect /
check link** if the IP changed. The app reads this file automatically at startup.
Collection and LSL start/stop state are never saved. Apply visualization changes
only the current session until you save them.

The small text file uses readable JSON. You can edit it while the app is closed;
colors are six-digit hex codes and plot_mode is `mean` or `overlay`. Invalid files
are reported without overwriting them; startup uses defaults if loading fails.

Select trials with Ctrl/Shift and click **Export selected**. The CSV includes every
selected spectrum, wavelength and physical unit, device model/serial, all eight
CIE fields, illuminance in lux when the instrument reports Y in lx/lux, and the
normalized approximate sRGB hex color used for the preview. Missing values are blank;
Y in other units is preserved without mislabelling it as lux. Instrument results
and status metadata are also preserved in JSON columns. Raw device XML is not saved.

`lsl_timestamp_s` is the exact host receipt timestamp used by both LSL streams,
whether or not streaming was enabled. It marks completion/receipt, not exposure
start. New acquisitions also save `received_unix_s` and `received_utc`, captured
immediately after reading the LSL clock, and a `clock_session` identifier. UTC follows
the computer's system clock; it is not independently verified against a time server.
LSL timestamps are monotonic seconds, not UTC or a universal network clock. Aligning
different computers requires LSL clock corrections (e.g. recorded with LabRecorder
in XDF); the CSV does not contain receiver clock corrections. Keep XDF recordings
when cross-computer synchronization is required. Timing reference:
https://labstreaminglayer.readthedocs.io/info/time_synchronization.html

**Open CSV** appends saved trials to the history, labels them `[file]`, and selects
them for preview. Select one to see its spectrum/color, or several compatible trials
to see mean ± SEM. Collection continues, but the preview stays on your selected
history until **View the last** returns to the latest live trial (or last loaded
trial if no live measurement exists). Loading never republishes old data to LSL.
Re-exporting preserves original timestamps. Invalid/incomplete files are rejected
before adding trials. Keep the CSV columns and metadata intact for reopening.

Old mean/SEM-only exports cannot restore individual trials, timestamps or color
values because that information was not saved. They are rejected with an explanation.

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
- `measurement_csv.py`: complete trial export and validated CSV loading.
- `probe_wifi.py`, `probe_usb.py`: connection diagnostics.

Historical recovery notes and backups remain in RECOVERY.md, USB_FINDINGS.md,
and recovery_backup/. Vendor binaries, backups and captures remain ignored by Git.
