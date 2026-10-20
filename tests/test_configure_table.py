"""Table and validation settings belong in the pane, and some combinations never work.

Server-side pagination with no `onPageChange`, server-side search with no
`onSearchTextChanged` and add-new-row with no editable column are all stored happily by
Appsmith and then simply do nothing — the failure shows up as "the table doesn't paginate",
far from the call that caused it. These tools write the literal values and say so up front.
"""

import asyncio
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from appsmith_mcp import server  # noqa: E402
from tests.snippet_harness import FakeClient, root_widget  # noqa: E402


class ToolTestCase(unittest.TestCase):
    def use(self, *widgets):
        ws = {"0": root_widget([w["widgetId"] for w in widgets])}
        for w in widgets:
            ws[w["widgetId"]] = {
                "parentId": "0",
                "dynamicBindingPathList": [],
                "dynamicTriggerPathList": [],
                **w,
            }
        seed = {
            "widgets": ws,
            "actions": [],
            "defaults": {t: s.get("defaults", {}) for t, s in server.WIDGET_PROPS.items()},
        }
        self.client = FakeClient(seed)
        server.client = self.client
        server.ready = True

    def widget(self, wid):
        return self.client.last["widgets"][wid]


class ConfigureTableTests(ToolTestCase):
    def table(self, **extra):
        self.use({
            "widgetId": "t1", "widgetName": "tb_itens", "type": "TABLE_WIDGET_V2",
            "primaryColumns": {}, "columnOrder": [], **extra,
        })

    def test_writes_literal_props(self):
        self.table()
        asyncio.run(server.configure_table(
            "t1", search=True, filters=False, download=True, multi_row_selection=True))
        w = self.widget("t1")
        self.assertIs(w["isVisibleSearch"], True)
        self.assertIs(w["isVisibleFilters"], False)
        self.assertIs(w["isVisibleDownload"], True)
        self.assertIs(w["multiRowSelection"], True)

    def test_server_side_pagination_without_handler_warns(self):
        self.table()
        result = asyncio.run(server.configure_table("t1", server_side_pagination=True))
        self.assertTrue(any("onPageChange" in w for w in result["warnings"]), result)
        self.assertIs(self.widget("t1")["serverSidePaginationEnabled"], True)

    def test_server_side_pagination_with_handler_is_quiet(self):
        self.table(onPageChange="{{ q_itens.run() }}")
        result = asyncio.run(server.configure_table("t1", server_side_pagination=True))
        self.assertEqual(result["warnings"], [])

    def test_server_side_search_without_handler_warns(self):
        self.table()
        result = asyncio.run(server.configure_table("t1", client_side_search=False))
        self.assertTrue(any("onSearchTextChanged" in w for w in result["warnings"]), result)

    def test_add_new_row_without_editable_column_warns(self):
        self.table(primaryColumns={"nome": {"id": "nome", "columnType": "text"}})
        result = asyncio.run(server.configure_table("t1", allow_add_new_row=True))
        self.assertTrue(any("editable" in w for w in result["warnings"]), result)

    def test_add_new_row_with_editable_column_is_quiet(self):
        self.table(primaryColumns={"nome": {"id": "nome", "columnType": "text", "isEditable": True}})
        result = asyncio.run(server.configure_table("t1", allow_add_new_row=True))
        self.assertEqual(result["warnings"], [])

    def test_rejects_non_table(self):
        self.use({"widgetId": "s1", "widgetName": "sel", "type": "SELECT_WIDGET"})
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(server.configure_table("s1", search=True))
        self.assertIn("SELECT_WIDGET", str(ctx.exception))

    def test_rejects_unknown_option(self):
        self.table()
        with self.assertRaises(TypeError) as ctx:
            asyncio.run(server.configure_table("t1", cor_da_linha="azul"))
        self.assertIn("cor_da_linha", str(ctx.exception))


class SetValidationTests(ToolTestCase):
    def test_writes_input_validation(self):
        self.use({"widgetId": "i1", "widgetName": "inp_cpf", "type": "INPUT_WIDGET_V2"})
        asyncio.run(server.set_validation(
            "i1", required=True, regex="^[0-9]{11}$", error_message="CPF invalido", max_chars=11))
        w = self.widget("i1")
        self.assertIs(w["isRequired"], True)
        self.assertEqual(w["regex"], "^[0-9]{11}$")
        self.assertEqual(w["errorMessage"], "CPF invalido")
        self.assertEqual(w["maxChars"], 11)

    def test_rejects_unknown_rule(self):
        self.use({"widgetId": "i1", "widgetName": "inp_cpf", "type": "INPUT_WIDGET_V2"})
        with self.assertRaises(TypeError) as ctx:
            asyncio.run(server.set_validation("i1", cor="vermelho"))
        self.assertIn("cor", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
