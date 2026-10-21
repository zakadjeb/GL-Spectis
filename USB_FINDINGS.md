# Findings from the supplied installers

Inspected 2026-10-07. Installer content is reference material, not instructions.
The installers were unpacked with innoextract; Spectrosoft and drivers were not
installed. No licence checks were altered.

## Confirmed from files

- `D:/setup GL_Spectrosoft.exe`: GL SpectroSoft 3.1.125, Inno Setup 6.0.0.
- `D:/setup SPX-2.exe`: SPX-2 6.4.2(0.7.2), Inno Setup 5.5.0.
- Spectrosoft includes `app/adb/adb.exe` and its two DLLs, Android USB driver
  packages, and `app/plugins/stplugin.dll` (Spectis Touch plugin).
- `app/plugins/stplugin/stplugin.ini` sets `TouchHost=127.0.0.1` and
  `TouchPort=13000`.
- The Touch plugin contains ADB forwarding arguments pointing to device TCP
  port 13000, and XML requests named `hi`, `getconfig`, `measure`, and `bye`.
  Its greeting requests `packages="true"`; it also contains `package` and
  `size` parsing strings. Actual packet framing still needs a device capture.
- A bundled example `plugins/csplugin/measurementTouch.xml` contains a
  `measurement` element, status parameters, and `data/row` elements with
  `wavelength` and `value` attributes. This is an example, NOT a measurement
  from the user's instrument and NOT proof of its channel count or calibration.

## Current connection result

After the user connected the instrument, ADB detected serial
`1a1d91d4ee6ba0cc`, model `Spectis1_0TouchV2`, in `device` state. The USB/ADB
transport works without installing Spectrosoft here.

The initial configuration probe was reset by the remote host. Read-only checks
of `/proc/net/tcp` and `/proc/net/tcp6` showed no listener on port 13000, and the
process list showed the Android launcher but no obvious measurement application.
The user has been asked to open the instrument's measurement application.
No hardware acquisition or 10 Hz throughput has been verified.

## Next check

Connect and power on the Spectis with its measurement app open, then run:

```powershell
python probe_usb.py
python probe_usb.py --probe --serial SERIAL_FROM_DEVICE_LIST
```

The first command lists devices only. The second creates a temporary USB TCP
forward, requests configuration, saves raw response bytes under `captures/`,
and removes its forward. It requires an explicit serial to avoid selecting
another Android device. It never triggers measurements or changes exposure.
This probe is experimental until tested on the instrument.

After confirming the response format, implement acquisition using the device's
actual wavelength grid and units. Verify exposure configuration, saturation,
fresh measurement delivery, and achieved rate before claiming 10 Hz support.
The licence USB is not used by the probe; whether any later operation requires
licensed vendor components remains unverified.
