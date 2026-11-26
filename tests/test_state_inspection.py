"""State inspection tools against the real inspect_state / dump_state snippets."""

import unittest
from unittest.mock import AsyncMock, patch

from appsmith_mcp import server
from appsmith_mcp.redaction import REDACTED
from tests.snippet_harness import FakeClient, root_widget

SEED = {
    "widgets": {
        "0": root_widget(["modal-1"]),
        "modal-1": {
            "widgetId": "modal-1", "widgetName": "PhotosModal", "type": "MODAL_WIDGET",
            "parentId": "0", "children": ["canvas-1"],
        },
        "canvas-1": {
            "widgetId": "canvas-1", "widgetName": "PhotosModalCanvas", "type": "CANVAS_WIDGET",
            "parentId": "modal-1", "children": ["text-2", "text-1"], "topRow": 0, "leftColumn": 0,
        },
        "text-1": {
            "widgetId": "text-1", "widgetName": "Title", "type": "TEXT_WIDGET",
            "parentId": "canvas-1", "topRow": 0, "leftColumn": 0, "isVisible": True,
        },
        "text-2": {
            "widgetId": "text-2", "widgetName": "Footer", "type": "TEXT_WIDGET",
            "parentId": "canvas-1", "topRow": 10, "leftColumn": 0, "isVisible": False,
        },
    },
    "datasources": [
        {
            "id": "ds-1", "name": "ShopDb", "pluginId": "plugin-1", "workspaceId": "ws-1",
            "datasourceStorages": {
                "env-1": {
                    "environmentId": "env-1",
                    "datasourceConfiguration": {
                        "url": "postgres://app:db-pass@db.example.com/shop",
                        "authentication": {"username": "app", "password": "db-pass"},
                        "headers": [{"key": "Authorization", "value": "Bearer live-token"}],
                    },
                }
            },
        }
    ],
    "actions": [
        {"config": {
            "id": "q-1", "name": "Orders", "pageId": "p1", "pluginId": "plugin-1",
            "datasource": {"id": "ds-1"},
            "actionConfiguration": {"headers": [{"key": "X-API-Key", "value": "live-key"}]},
        }}
    ],
    "evalTree": {
        "appsmith": {"store": {"branch": "001", "access_token": "live-token"}},
        "Table1": {"selectedRow": {"id": 7, "rows": [{"name": "Alice"}]}},
    },
}


class StateInspectionToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = FakeClient(SEED)
        for p in (
            patch.object(server, "ensure_ready", new=AsyncMock()),
            patch.object(server, "client", self.client),
        ):
            p.start()
            self.addCleanup(p.stop)

    async def test_get_store_filters_keys_and_redacts_tokens(self):
        self.assertEqual(
            await server.get_store(["branch", "access_token", "missing"]),
            {"store": {"branch": "001", "access_token": REDACTED}},
        )
        self.assertEqual(
            await server.get_store(),
            {"store": {"branch": "001", "access_token": REDACTED}},
        )

    async def test_eval_value_reads_single_path(self):
        self.assertEqual(
            await server.eval_value("Table1.selectedRow.id"),
            {"path": "Table1.selectedRow.id", "found": True, "value": 7},
        )

    async def test_eval_value_maps_several_paths_and_redacts_by_last_segment(self):
        self.assertEqual(
            await server.eval_value(
                ["Table1.selectedRow.rows[0].name", "appsmith.store.access_token", "Table1.nope"]
            ),
            {
                "Table1.selectedRow.rows[0].name": "Alice",
                "appsmith.store.access_token": REDACTED,
                "Table1.nope": None,
            },
        )

    async def test_eval_value_never_evaluates_code(self):
        result = await server.eval_value("fetch('/api/v1/actions')")

        self.assertFalse(result["found"])
        self.assertIn("only property names", result["error"])

    async def test_list_children_returns_direct_children_sorted_by_position(self):
        result = await server.list_children("PhotosModalCanvas")

        self.assertEqual([c["id"] for c in result], ["text-1", "text-2"])
        self.assertEqual([c["isVisible"] for c in result], [True, False])
        self.assertEqual(await server.list_children("missing"), {"error": "parent missing not found"})

    async def test_get_datasource_redacts_secrets_in_every_environment(self):
        result = await server.get_datasource("ShopDb")

        config = result["environments"][0]["datasourceConfiguration"]
        self.assertEqual(result["id"], "ds-1")
        self.assertEqual(config["authentication"], {"username": "app", "password": REDACTED})
        self.assertEqual(config["headers"][0]["value"], REDACTED)
        self.assertEqual(config["url"], f"postgres://app:{REDACTED}@db.example.com/shop")

    async def test_dump_state_verbose_redacts_datasources_and_queries(self):
        result = await server.dump_state(verbose=True)

        storage = result["datasources"][0]["datasourceStorages"]["env-1"]["datasourceConfiguration"]
        self.assertEqual(storage["authentication"]["password"], REDACTED)
        self.assertEqual(
            result["queries"][0]["actionConfiguration"]["headers"][0]["value"], REDACTED
        )
        self.assertNotIn("live-", repr(result))
        self.assertNotIn("db-pass", repr(result))


if __name__ == "__main__":
    unittest.main()
