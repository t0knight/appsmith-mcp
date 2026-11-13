import asyncio
import unittest

from appsmith_mcp import server
from tests.snippet_harness import FakeClient, root_widget


def lint(*widgets, actions=("q_itens",)):
    ws = {"0": root_widget([w["widgetId"] for w in widgets])}
    for w in widgets:
        ws[w["widgetId"]] = {"parentId": "0", "dynamicBindingPathList": [], "dynamicTriggerPathList": [], **w}
    server.client = FakeClient({"widgets": ws, "actions": [{"config": {"id": a, "name": a}} for a in actions]})
    server.ready = True
    out = asyncio.run(server.lint_design())
    return {(f["rule"], f["widget"]) for f in out["findings"]}, out


class LintDesignTests(unittest.TestCase):
    def test_binding_hidden_behind_visual_control(self):
        found, _ = lint({"widgetId": "a", "widgetName": "sel_a", "type": "SELECT_WIDGET",
                         "labelText": "A", "tooltip": "x",
                         "isVisible": "{{ x }}", "dynamicBindingPathList": [{"key": "isVisible"}]})
        self.assertIn(("binding_hidden_in_ui", "sel_a"), found)

    def test_binding_in_js_mode_is_fine(self):
        found, _ = lint({"widgetId": "a", "widgetName": "sel_a", "type": "SELECT_WIDGET",
                         "isVisible": "{{ x }}", "dynamicBindingPathList": [{"key": "isVisible"}],
                         "dynamicPropertyPathList": [{"key": "isVisible"}]})
        self.assertNotIn(("binding_hidden_in_ui", "sel_a"), found)

    def test_simple_query_data_is_fine_but_transformed_data_is_flagged(self):
        found, _ = lint(
            {"widgetId": "a", "widgetName": "tb_ok", "type": "TABLE_WIDGET_V2", "tableData": "{{q_itens.data}}",
             "dynamicBindingPathList": [{"key": "tableData"}]},
            {"widgetId": "b", "widgetName": "tb_map", "type": "TABLE_WIDGET_V2",
             "tableData": "{{ q_itens.data.map(r => r) }}",
             "dynamicBindingPathList": [{"key": "tableData"}], "dynamicPropertyPathList": [{"key": "tableData"}]},
        )
        self.assertNotIn(("binding_hidden_in_ui", "tb_ok"), found)
        self.assertNotIn(("data_transformed_in_binding", "tb_ok"), found)
        self.assertIn(("data_transformed_in_binding", "tb_map"), found)

    def test_spaced_query_binding_is_hidden(self):
        found, _ = lint({"widgetId": "a", "widgetName": "tb_sp", "type": "TABLE_WIDGET_V2",
                         "tableData": "{{ q_itens.data }}", "dynamicBindingPathList": [{"key": "tableData"}]})
        self.assertIn(("binding_hidden_in_ui", "tb_sp"), found)

    def test_default_widget_names_are_flagged(self):
        found, _ = lint({"widgetId": "a", "widgetName": "IconButton1", "type": "ICON_BUTTON_WIDGET"},
                        {"widgetId": "b", "widgetName": "bt_salvar", "type": "BUTTON_WIDGET"})
        self.assertIn(("default_widget_name", "IconButton1"), found)
        self.assertNotIn(("default_widget_name", "bt_salvar"), found)

    def test_modal_query_rule_no_longer_recommends_the_store(self):
        modal = {"widgetId": "m", "widgetName": "md_a", "type": "MODAL_WIDGET"}
        canvas = {"widgetId": "mc", "widgetName": "c", "type": "CANVAS_WIDGET", "parentId": "m"}
        table = {"widgetId": "t", "widgetName": "tb_m", "type": "TABLE_WIDGET_V2", "parentId": "mc",
                 "tableData": "{{q_itens.data}}", "dynamicBindingPathList": [{"key": "tableData"}]}
        _, out = lint(modal, canvas, table)
        hits = [f for f in out["findings"] if f["rule"] == "modal_binds_query_data"]
        self.assertTrue(hits)
        self.assertNotIn("appsmith.store", hits[0]["detail"])


if __name__ == "__main__":
    unittest.main()
