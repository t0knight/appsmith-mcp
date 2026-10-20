"""Exercise the registered MCP tools, not only their Python keyword callers."""

import json
import unittest
from unittest.mock import AsyncMock, patch

from appsmith_mcp import server
from tests.snippet_harness import FakeClient, root_widget


def payload(result, many=False):
    if isinstance(result, tuple):
        result = result[1]
    if isinstance(result, dict):
        return result.get("result", result)
    decoded = [json.loads(block.text) for block in result]
    return decoded if many else decoded[0]


class MCPContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.previous_client, self.previous_ready = server.client, server.ready
        widgets = {
            "0": root_widget(["t1", "i1", "b1"]),
            "t1": {"widgetId": "t1", "widgetName": "tb_itens", "type": "TABLE_WIDGET_V2",
                   "primaryColumns": {}, "columnOrder": [], "parentId": "0",
                   "dynamicBindingPathList": [], "dynamicTriggerPathList": []},
            "i1": {"widgetId": "i1", "widgetName": "inp_cpf", "type": "INPUT_WIDGET_V2",
                   "parentId": "0", "dynamicBindingPathList": [], "dynamicTriggerPathList": []},
            "b1": {"widgetId": "b1", "widgetName": "bt_salvar", "type": "BUTTON_WIDGET",
                   "parentId": "0", "dynamicBindingPathList": [], "dynamicTriggerPathList": []},
        }
        self.client = FakeClient({"widgets": widgets, "defaults": {
            name: schema.get("defaults", {}) for name, schema in server.WIDGET_PROPS.items()
        }})
        server.client, server.ready = self.client, True

    def tearDown(self):
        server.client, server.ready = self.previous_client, self.previous_ready

    async def test_registered_table_call_preserves_false_zero_and_empty_text(self):
        result = payload(await server.mcp.call_tool("configure_table", {
            "widget_id": "t1", "search": False, "total_record_count": 0,
            "default_search_text": "", "inline_save": "ROW_LEVEL",
        }))
        self.assertTrue(result["persisted"])
        self.assertEqual(result["applied"], {
            "isVisibleSearch": False, "totalRecordsCount": 0,
            "defaultSearchText": "", "inlineEditingSaveOption": "ROW_LEVEL",
        })
        self.assertIs(self.client.last["widgets"]["t1"]["isVisibleSearch"], False)

    async def test_registered_validation_call_writes_named_rules(self):
        result = payload(await server.mcp.call_tool("set_validation", {
            "widget_id": "i1", "required": False, "regex": "^[0-9]{11}$",
            "error_message": "CPF invalido", "max_chars": 11,
        }))
        self.assertTrue(result["persisted"])
        self.assertEqual(result["applied"]["regex"], "^[0-9]{11}$")
        self.assertIs(self.client.last["widgets"]["i1"]["isRequired"], False)

    async def test_schema_advertises_named_options(self):
        tools = {tool.name: tool for tool in await server.mcp.list_tools()}
        schema = tools["configure_table"].inputSchema
        self.assertNotIn("options", schema["properties"])
        self.assertIn("search", schema["properties"])
        self.assertEqual(schema["required"], ["widget_id"])
        self.assertIs(schema["additionalProperties"], False)
        self.assertNotIn("rules", tools["set_validation"].inputSchema["properties"])

    async def test_unknown_argument_fails_before_editor_read(self):
        for name, args in [
            ("configure_table", {"widget_id": "t1", "serch": True}),
            ("set_validation", {"widget_id": "i1", "reqired": True}),
        ]:
            with self.subTest(name=name), self.assertRaises(Exception):
                await server.mcp.call_tool(name, args)
        self.assertEqual(self.client.calls, [])

    async def test_invalid_inline_save_fails_before_editor_read(self):
        with self.assertRaises(Exception):
            await server.mcp.call_tool("configure_table", {
                "widget_id": "t1", "inline_save": "INVALID",
            })
        self.assertEqual(self.client.calls, [])

    async def test_actual_layout_save_failure_is_not_reported_as_applied(self):
        self.client.seed["responses"] = [{
            "match": "/api/v1/layouts/", "method": "PUT", "status": 500,
            "body": {"responseMeta": {"success": False}},
        }]
        calls = [
            ("configure_table", {"widget_id": "t1", "search": True}),
            ("set_validation", {"widget_id": "i1", "required": True}),
            ("set_widget_events", {"events": [{"widget": "b1", "events": {
                "onClick": {"action": "show_alert", "message": "Teste"},
            }}]}),
        ]
        for name, args in calls:
            with self.subTest(name=name), self.assertRaisesRegex(Exception, "HTTP 500"):
                await server.mcp.call_tool(name, args)

    async def test_unconfirmed_save_fails_closed(self):
        for result in [[], None, [{"widgetId": "i1"}], [{"widgetId": "i1", "persisted": False}]]:
            with self.subTest(result=result), patch.object(
                server, "update_widgets", new=AsyncMock(return_value=result)
            ), self.assertRaises(Exception):
                await server.mcp.call_tool("set_validation", {"widget_id": "i1", "required": True})

    async def test_partial_event_batch_preserves_success_and_failure(self):
        outcomes = [{"widgetId": "b1", "persisted": True},
                    {"widgetId": "i1", "error": "save failed: HTTP 500"}]
        with patch.object(server, "update_widgets", new=AsyncMock(return_value=outcomes)):
            result = payload(await server.mcp.call_tool("set_widget_events", {"events": [
                {"widget": "b1", "events": {"onClick": {"action": "show_alert", "message": "ok"}}},
                {"widget": "i1", "events": {"onTextChanged": {"action": "show_alert", "message": "erro"}}},
            ]}), many=True)
        self.assertTrue(result[0]["ok"])
        self.assertTrue(result[0]["persisted"])
        self.assertFalse(result[1]["ok"])
        self.assertIn("HTTP 500", result[1]["error"])

    async def test_repeated_event_reports_only_the_final_persisted_value(self):
        result = payload(await server.mcp.call_tool("set_widget_events", {"events": [
            {"widget": "b1", "events": {"onClick": {"action": "show_alert", "message": "first"}}},
            {"widget": "b1", "events": {"onClick": {"action": "show_alert", "message": "second"}}},
        ]}), many=True)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["persisted"])
        self.assertEqual(result[0]["code"], "{{ showAlert('second') }}")
        self.assertEqual(self.client.last["widgets"]["b1"]["onClick"], result[0]["code"])


if __name__ == "__main__":
    unittest.main()
