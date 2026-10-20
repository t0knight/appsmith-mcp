import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SNIPPET = REPO_ROOT / "src" / "appsmith_mcp" / "snippets" / "inspect_state.js"

STATE = {
    "entities": {
        "canvasWidgets": {
            "modal-1": {
                "widgetId": "modal-1",
                "widgetName": "ModalFotos",
                "type": "MODAL_WIDGET",
                "parentId": "0",
            },
            "canvas-1": {
                "widgetId": "canvas-1",
                "widgetName": "CanvasModalFotos",
                "type": "CANVAS_WIDGET",
                "parentId": "modal-1",
                "topRow": 0,
                "leftColumn": 0,
            },
            "text-1": {
                "widgetId": "text-1",
                "widgetName": "Titulo",
                "type": "TEXT_WIDGET",
                "parentId": "canvas-1",
            },
        },
        "datasources": {
            "list": [
                {
                    "id": "ds-1",
                    "name": "Banco",
                    "pluginId": "plugin-1",
                    "workspaceId": "ws-1",
                    "datasourceStorages": {
                        "env-1": {
                            "environmentId": "env-1",
                            "datasourceConfiguration": {
                                "authentication": {
                                    "username": "app",
                                    "password": "senha-real",
                                },
                                "headers": [
                                    {
                                        "key": "Authorization",
                                        "value": "Bearer segredo-real",
                                    }
                                ],
                            },
                        }
                    },
                }
            ]
        },
    },
    "evaluations": {
        "tree": {
            "appsmith": {
                "store": {"filial": "001", "access_token": "token-real"}
            },
            "Tabela1": {"selectedRow": {"id": 7}},
        }
    },
}


def inspect(mode: str, argument=None):
    script = f"""
const fs = require('fs');
global.MODE = {json.dumps(mode)};
global.ARG = {json.dumps(argument)};
global.window = {{ __store: {{ getState: () => ({json.dumps(STATE)}) }} }};
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


class InspectStateSnippetTests(unittest.TestCase):
    def test_get_store_filters_keys_and_redacts_tokens(self):
        result = inspect("get_store", {"keys": ["filial", "access_token"]})

        self.assertEqual(
            result,
            {"store": {"filial": "001", "access_token": "[REDACTED]"}},
        )

    def test_eval_value_resolves_path_without_evaluating_code(self):
        result = inspect("eval_value", {"path": "Tabela1.selectedRow.id"})
        secret = inspect("eval_value", {"path": "appsmith.store.access_token"})

        self.assertEqual(
            result,
            {"path": "Tabela1.selectedRow.id", "found": True, "value": 7},
        )
        self.assertEqual(secret["value"], "[REDACTED]")

    def test_list_children_returns_only_direct_children(self):
        result = inspect("list_children", {"parent_id": "modal-1"})

        self.assertEqual([item["id"] for item in result], ["canvas-1"])

    def test_get_datasource_returns_effective_config_with_secrets_redacted(self):
        result = inspect("get_datasource", {"datasource_id": "ds-1"})

        config = result["environments"][0]["datasourceConfiguration"]
        self.assertEqual(config["authentication"]["username"], "app")
        self.assertEqual(config["authentication"]["password"], "[REDACTED]")
        self.assertEqual(config["headers"][0]["value"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
