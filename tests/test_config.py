import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ConfigEnvironmentTests(unittest.TestCase):
    def _read_config(self, override=None):
        env = os.environ.copy()
        env.pop("APPSMITH_BIDI_PORT", None)
        if override is not None:
            env["APPSMITH_BIDI_PORT"] = override
        program = """
import json
from appsmith_mcp import config
print(json.dumps({"port": config.BIDI_PORT, "url": config.BIDI_WS_URL}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", program],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def test_default_bidi_port(self):
        self.assertEqual(
            self._read_config(),
            {"port": 9222, "url": "ws://127.0.0.1:9222/session"},
        )

    def test_environment_overrides_bidi_port(self):
        self.assertEqual(
            self._read_config("9333"),
            {"port": 9333, "url": "ws://127.0.0.1:9333/session"},
        )


if __name__ == "__main__":
    unittest.main()
