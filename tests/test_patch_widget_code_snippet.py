import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SNIPPET = REPO_ROOT / "src" / "appsmith_mcp" / "snippets" / "patch_widget_code.js"


def run_patch(current: str, old: str, new: str) -> dict:
    state = {
        "entities": {
            "canvasWidgets": {
                "widget-1": {
                    "widgetId": "widget-1",
                    "widgetName": "Custom1",
                    "type": "CUSTOM_WIDGET",
                    "srcDoc": {"css": current},
                }
            }
        }
    }
    script = f"""
const fs = require('fs');
global.EDITS = [{{
  widget_id: 'widget-1', field: 'css',
  old: {json.dumps(old)}, new: {json.dumps(new)}
}}];
global.window = {{ __store: {{ getState: () => ({json.dumps(state)}) }} }};
const result = eval(fs.readFileSync({json.dumps(str(SNIPPET))}, 'utf8'));
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise AssertionError(completed.stderr)
    return json.loads(completed.stdout)


class PatchWidgetCodeSnippetTests(unittest.TestCase):
    def test_uses_unique_whitespace_normalized_match_as_fallback(self):
        result = run_patch(
            ":root {\n    --brand: #651C32;\n}\n",
            ":root{--brand:#651C32;}",
            ":root{--brand:#000000;}",
        )

        self.assertNotIn("error", result["results"][0])
        self.assertEqual(result["results"][0]["replacements"], 1)
        self.assertEqual(result["results"][0]["matchMode"], "normalized")
        self.assertIn("#000000", result["fields"][0]["value"])

    def test_refuses_ambiguous_normalized_match(self):
        result = run_patch(
            ".item { color: red; }\n.item {\n  color: red;\n}",
            ".item{color:red;}",
            ".item{color:blue;}",
        )

        self.assertIn("matches 2 times", result["results"][0]["error"])
        self.assertEqual(result["fields"], [])


if __name__ == "__main__":
    unittest.main()
