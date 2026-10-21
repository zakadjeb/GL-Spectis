# Spectis recovery assessment — 7 October 2026

The connected instrument identifies as Spectis1_0TouchV2 over ADB, USB serial
1a1d91d4ee6ba0cc. Android boots and USB communication works.

The package manager lists no GL measurement app, including disabled and retained
uninstalled packages. No saved APK was found in the searched app, temporary,
internal media, and mounted external-storage directories. The supplied Windows
Spectrosoft installer contains no APK. This is not proof that no recovery package
exists elsewhere.

The instrument's `/cache/recovery/last_log` explicitly records formatting `/data`
and `/cache` and “Data wipe complete.” Its header is dated 18 May 2026 according
to the device clock; that date has not been independently verified. This explains
the missing app, but does not establish who initiated the wipe.

## Preserved data

Copied to `recovery_backup/` without modifying the instrument:

- `/data/data/gloptic` including calibration/profile files and touch_profile.tar.
- The SD card measurements folder: ADB reports 438 files, 13,340,594 bytes.
- The recovery log.
- A local SHA-256 manifest for the copied files.

These copies are not a complete device image. The presence of calibration files
does not establish their validity, completeness, or suitability for restored
software. Do not replace them with profiles from a different instrument.

## Recovery route

Obtain the correct on-instrument application APK or manufacturer recovery package
for the Spectis 1.0 Touch + Flicker, hardware identified as Spectis1_0TouchV2.
Ask GL Optic whether reinstalling the app is sufficient, how to preserve and
validate the remaining calibration, and whether service is required. Do not
factory-reset or reflash the instrument while these questions remain unresolved.

Official support: https://gloptic.com/services/support/

Suggested message (not sent):

> Our GL Spectis 1.0 Touch + Flicker boots into Android, but its measurement
> application is missing. ADB reports model Spectis1_0TouchV2, USB serial
> 1a1d91d4ee6ba0cc, Android 6.0.1, build 2.1.0-ga-rc2 release-keys. A recovery log
> records a data wipe. Files remain under /data/data/gloptic/profiles and have
> been backed up, together with SD-card measurements. Please provide the correct
> application/recovery package and instructions for this hardware, including
> confirmation of calibration preservation and validation. We have the original
> Windows Spectrosoft installer and licence USB. We can supply the instrument's
> physical serial number separately.

Once the measurement software is restored and calibration is verified, resume
the direct USB spectrum-to-LSL work and measure achievable acquisition rate.
