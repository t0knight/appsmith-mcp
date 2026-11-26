import unittest
from unittest.mock import AsyncMock, patch

from appsmith_mcp import server
from tests.snippet_harness import FakeClient, root_widget


def saved_action(action_id, name, body):
    return {"config": {
        "id": action_id, "name": name, "pluginId": "plugin-mssql",
        "actionConfiguration": {"body": body},
    }}


class ExecuteQueriesPolicyTests(unittest.IsolatedAsyncioTestCase):
    """execute_queries against the real get_queries / execute_queries snippets."""

    async def asyncSetUp(self):
        self.client = FakeClient(
            {
                "widgets": {"0": root_widget()},
                "actions": [
                    saved_action("write-query", "Delete_customer", "DELETE FROM customers"),
                    saved_action("read-query", "List_customers", "SELECT * FROM customers"),
                    saved_action("update-query", "Update_customer", "UPDATE customers SET active = 1"),
                ],
                "plugins": [{"id": "plugin-mssql", "packageName": "mssql-plugin"}],
            }
        )
        patches = (
            patch.object(server, "ensure_ready", new=AsyncMock()),
            patch.object(server, "client", self.client),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def executions(self):
        return [
            f for call in self.client.calls for f in call["fetches"]
            if f["url"] == "/api/v1/actions/execute"
        ]

    async def test_execute_queries_runs_only_actions_approved_as_read_only(self):
        result = await server.execute_queries(["write-query", "read-query"])

        self.assertEqual([r["id"] for r in result], ["write-query", "read-query"])
        self.assertTrue(result[0]["blocked"])
        self.assertFalse(result[0]["ok"])
        self.assertEqual(result[0]["name"], "Delete_customer")
        self.assertEqual(
            result[0]["error"],
            "Execution blocked by the read-only policy: only SELECT or WITH ... SELECT is allowed.",
        )
        self.assertTrue(result[1]["ok"])
        self.assertNotIn("blocked", result[1])
        self.assertEqual(len(self.executions()), 1)

    async def test_execute_queries_does_not_dispatch_when_every_action_is_blocked(self):
        result = await server.execute_queries(["update-query", "write-query"])

        self.assertTrue(all(r["blocked"] for r in result))
        self.assertEqual(len(self.client.calls), 1)  # only the metadata read
        self.assertEqual(self.executions(), [])

    async def test_execute_queries_blocks_unknown_query_ids(self):
        result = await server.execute_queries(["missing-query"])

        self.assertEqual(
            result,
            [{
                "id": "missing-query",
                "ok": False,
                "blocked": True,
                "error": "Execution blocked by the read-only policy: query metadata not found.",
            }],
        )
        self.assertEqual(self.executions(), [])


class UnsafeExecutionGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ensure_ready = AsyncMock()
        self.run_snippet = AsyncMock()
        patches = (
            patch.object(server, "ensure_ready", new=self.ensure_ready),
            patch.object(server.client, "run_snippet", new=self.run_snippet),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    async def test_execute_js_functions_is_blocked_by_default_without_touching_browser(self):
        with patch.object(server, "ALLOW_UNSAFE_EXECUTION", False):
            result = await server.execute_js_functions(
                [{"js_object_id": "js-1", "function_name": "run"}]
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["jsObjectId"], "js-1")
        self.assertEqual(result[0]["functionName"], "run")
        self.assertFalse(result[0]["ok"])
        self.assertTrue(result[0]["blocked"])
        self.assertIn("APPSMITH_ALLOW_UNSAFE_EXECUTION=1", result[0]["error"])
        self.ensure_ready.assert_not_awaited()
        self.run_snippet.assert_not_awaited()

    async def test_run_command_is_blocked_by_default_without_touching_browser(self):
        with patch.object(server, "ALLOW_UNSAFE_EXECUTION", False):
            result = await server.run_command("fetch('/api/v1/actions/execute')")

        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertIn("APPSMITH_ALLOW_UNSAFE_EXECUTION=1", result["error"])
        self.ensure_ready.assert_not_awaited()
        self.run_snippet.assert_not_awaited()

    async def test_unsafe_tools_run_when_the_user_allows_them(self):
        self.run_snippet.side_effect = [[{"ok": True}], 42]
        with patch.object(server, "ALLOW_UNSAFE_EXECUTION", True):
            js_result = await server.execute_js_functions(
                [{"js_object_id": "js-1", "function_name": "run"}]
            )
            command_result = await server.run_command("1 + 41")

        self.assertEqual(js_result, [{"ok": True}])
        self.assertEqual(command_result, {"result": 42})
        self.assertEqual(self.run_snippet.await_count, 2)


if __name__ == "__main__":
    unittest.main()
