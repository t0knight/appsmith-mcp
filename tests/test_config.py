import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ConfigEnvironmentTests(unittest.TestCase):
    def test_environment_selects_bidi_port_and_firefox_profile(self):
        env = os.environ.copy()
        env["APPSMITH_BIDI_PORT"] = "9333"
        env["APPSMITH_FIREFOX_PROFILE"] = r"C:\profiles\appsmith-9333"
        program = """
import json
from appsmith_mcp import config
print(json.dumps({
    "port": config.BIDI_PORT,
    "ws_url": config.BIDI_WS_URL,
    "profile": config.FIREFOX_PROFILE,
}))
"""

        result = subprocess.run(
            [sys.executable, "-c", program],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "port": 9333,
                "ws_url": "ws://127.0.0.1:9333/session",
                "profile": r"C:\profiles\appsmith-9333",
            },
        )


if __name__ == "__main__":
    unittest.main()
