"""First-run setup for start_monitor.bat; uses only the standard library."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parent
PROBE = "import tkinter; import numpy; import matplotlib.backends.backend_tkagg; import pylsl"


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def prepare(root=ROOT):
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    requirements = root / "requirements.txt"
    marker = environment / ".spectis-requirements"
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not python.is_file():
        print("Creating a private Python environment in .venv ...", flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)

    repair = False
    ready = marker.is_file() and marker.read_text().strip() == fingerprint
    if ready:
        try:
            run([str(python), "-c", PROBE], capture_output=True)
        except subprocess.CalledProcessError:
            ready = False
            repair = True
    if not ready:
        print("Installing/checking required libraries. Internet access may be needed; please wait ...", flush=True)
        # A failed setup must never leave a success marker behind.
        marker.unlink(missing_ok=True)
        run([str(python), "-m", "ensurepip", "--upgrade"])
        run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
             *(["--force-reinstall"] if repair else []), "-r", str(requirements)])
        run([str(python), "-c", PROBE])
        marker.write_text(fingerprint + "\n")
    return python


def main():
    if sys.version_info < (3, 10):
        print("Please install Python 3.10 or newer, including pip and Tcl/Tk.")
        return 1
    try:
        import tkinter  # Tcl/Tk is part of Python's installer, not a pip package.
    except ImportError:
        print("Tkinter is missing. Modify your Python installation and enable Tcl/Tk, then retry.")
        return 1
    try:
        python = prepare()
    except (OSError, subprocess.CalledProcessError) as exc:
        print("\nSetup could not finish: {}".format(exc))
        print("Check your internet connection and that this folder is writable, then run start_monitor.bat again.")
        print("If the error refers to a broken .venv, close the monitor, rename .venv, and retry.")
        return 1
    print("Starting GL Spectis monitor ...", flush=True)
    return subprocess.call([str(python), str(ROOT / "monitor.py")], cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
