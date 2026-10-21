import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="spectis setup ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "requirements.txt").write_text("numpy>=1.24,<3\n")
        self.python = self.root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.marker = self.root / ".venv/.spectis-requirements"

    def create_environment(self, path):
        self.python.parent.mkdir(parents=True)
        self.python.touch()

    def test_first_run_then_offline_reuse_and_changed_requirements(self):
        with patch.object(bootstrap.venv.EnvBuilder, "create", side_effect=self.create_environment) as create, patch.object(bootstrap, "run") as run:
            self.assertEqual(bootstrap.prepare(self.root), self.python)
            create.assert_called_once()
            self.assertTrue(self.marker.exists())
            self.assertIn(str(self.root / "requirements.txt"), run.call_args_list[1].args[0])
            run.reset_mock()
            bootstrap.prepare(self.root)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0], [str(self.python), "-c", bootstrap.PROBE])
            (self.root / "requirements.txt").write_text("numpy>=2,<3\n")
            run.reset_mock()
            bootstrap.prepare(self.root)
            self.assertEqual(run.call_count, 3)

    def test_failed_install_leaves_no_success_marker(self):
        with patch.object(bootstrap.venv.EnvBuilder, "create", side_effect=self.create_environment), patch.object(bootstrap, "run", side_effect=subprocess.CalledProcessError(1, "pip")):
            with self.assertRaises(subprocess.CalledProcessError):
                bootstrap.prepare(self.root)
        self.assertFalse(self.marker.exists())

    def test_broken_import_forces_reinstallation(self):
        with patch.object(bootstrap.venv.EnvBuilder, "create", side_effect=self.create_environment), patch.object(bootstrap, "run"):
            bootstrap.prepare(self.root)
        with patch.object(bootstrap, "run", side_effect=[subprocess.CalledProcessError(1, "probe"), None, None, None]) as run:
            bootstrap.prepare(self.root)
        self.assertIn("--force-reinstall", run.call_args_list[2].args[0])


if __name__ == "__main__":
    unittest.main()
