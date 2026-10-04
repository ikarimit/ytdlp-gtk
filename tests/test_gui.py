"""Runs tests/gui_scenarios.py in a subprocess and checks every scenario passed (needs a display)."""
import os
import subprocess
import sys
import unittest
from pathlib import Path


@unittest.skipUnless(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"), "needs a display")
class GuiScenarios(unittest.TestCase):
    def test_scenarios(self):
        out = subprocess.run([sys.executable, str(Path(__file__).with_name("gui_scenarios.py"))],
                             capture_output=True, text=True, timeout=180).stdout
        lines = [l for l in out.splitlines() if l.startswith(("PASS", "FAIL", "DONE"))]
        self.assertIn("DONE", lines, out)
        failures = [l for l in lines if l.startswith("FAIL")]
        self.assertFalse(failures, "\n".join(failures))
        self.assertGreaterEqual(len([l for l in lines if l.startswith("PASS")]), 10)


if __name__ == "__main__":
    unittest.main()
