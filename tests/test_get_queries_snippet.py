import asyncio
import unittest

from appsmith_mcp.snippets import GET_QUERIES_JS
from tests.snippet_harness import FakeClient, root_widget


class GetQueriesSnippetTests(unittest.TestCase):
    def run_snippet(self, ids):
        client = FakeClient(
            {
                "widgets": {"0": root_widget()},
                "actions": [
                    {"config": {
                        "id": "query-1", "name": "Lookup", "pluginId": "plugin-1",
                        "actionConfiguration": {"body": "SELECT 1"},
                    }},
                    {"config": {
                        "id": "query-2", "name": "Other", "pluginId": "plugin-2",
                        "actionConfiguration": {"httpMethod": "GET"},
                    }},
                ],
                "plugins": [
                    {"id": "plugin-1", "packageName": "mssql-plugin"},
                    {"id": "plugin-2", "packageName": "restapi-plugin"},
                ],
            }
        )
        return asyncio.run(client.run_snippet(GET_QUERIES_JS, json_constants={"IDS": ids}))

    def test_returns_plugin_package_name_and_configuration_for_requested_ids(self):
        self.assertEqual(
            self.run_snippet(["query-1"]),
            [
                {
                    "id": "query-1",
                    "name": "Lookup",
                    "pluginPackageName": "mssql-plugin",
                    "actionConfiguration": {"body": "SELECT 1"},
                }
            ],
        )

    def test_unknown_ids_are_left_out(self):
        self.assertEqual(self.run_snippet(["missing"]), [])


if __name__ == "__main__":
    unittest.main()
