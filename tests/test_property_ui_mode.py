"""Widget properties must land the way the Appsmith property pane stores them.

A JS-convertible property (switch, dropdown, colour, one-click data selector...) only shows
its `{{ }}` code in the editor when its path is in `dynamicPropertyPathList` (the "JS" toggle).
Without it the pane renders the visual control, which can't display a binding — so the field
looks empty/wrong to whoever maintains the page.

Writing such a binding is refused by `panel_policy` unless the exact path is authorised,
so the tests here pass `allow_bindings=[...]`: they exist to prove the JS toggle is set
once the write IS authorised.
"""

import asyncio
import unittest

from appsmith_mcp import server
from tests.snippet_harness import FakeClient, find_node, keys, root_widget


def seed_with(*widgets, actions=()):
    ws = {"0": root_widget([w["widgetId"] for w in widgets])}
    for w in widgets:
        ws[w["widgetId"]] = {"parentId": "0", "dynamicBindingPathList": [], "dynamicTriggerPathList": [], **w}
    return {"widgets": ws, "actions": list(actions),
            "defaults": {t: s.get("defaults", {}) for t, s in server.WIDGET_PROPS.items()}}


def run(coro):
    return asyncio.run(coro)


class PropertyUiModeTests(unittest.TestCase):
    def use(self, seed):
        self.client = FakeClient(seed)
        server.client = self.client
        server.ready = True

    def widget(self, wid):
        return self.client.last["widgets"][wid]

    def test_bound_switch_property_turns_on_js_mode(self):
        self.use(seed_with({"widgetId": "s1", "widgetName": "sel_a", "type": "SELECT_WIDGET"}))
        run(server.update_widgets([{"widget_id": "s1", "props": {"isVisible": "{{ chk.isChecked }}"}}],
                                  allow_bindings=["sel_a.isVisible"]))
        w = self.widget("s1")
        self.assertIn("isVisible", keys(w["dynamicBindingPathList"]))
        self.assertIn("isVisible", keys(w.get("dynamicPropertyPathList")))
        persisted = find_node(self.client.persisted_dsl(), "s1")
        self.assertIn("isVisible", keys(persisted.get("dynamicPropertyPathList")))

    def test_literal_value_turns_js_mode_off(self):
        self.use(seed_with({"widgetId": "s1", "widgetName": "sel_a", "type": "SELECT_WIDGET",
                            "isVisible": "{{ x }}", "dynamicBindingPathList": [{"key": "isVisible"}],
                            "dynamicPropertyPathList": [{"key": "isVisible"}]}))
        run(server.update_widgets([{"widget_id": "s1", "props": {"isVisible": True}}]))
        self.assertNotIn("isVisible", keys(self.widget("s1").get("dynamicPropertyPathList")))

    def test_simple_query_table_data_is_normalized_for_the_data_dropdown(self):
        self.use(seed_with({"widgetId": "t1", "widgetName": "tb_a", "type": "TABLE_WIDGET_V2"}))
        run(server.update_widgets([{"widget_id": "t1", "props": {"tableData": "{{ q_itens.data }}"}}]))
        w = self.widget("t1")
        self.assertEqual(w["tableData"], "{{q_itens.data}}")
        self.assertIn("tableData", keys(w["dynamicBindingPathList"]))
        self.assertNotIn("tableData", keys(w.get("dynamicPropertyPathList")))

    def test_transformed_table_data_is_shown_as_code(self):
        self.use(seed_with({"widgetId": "t1", "widgetName": "tb_a", "type": "TABLE_WIDGET_V2"}))
        run(server.update_widgets([{"widget_id": "t1", "props": {"tableData": "{{ q_itens.data.filter(r => r.ativo) }}"}}],
                                  allow_bindings=["tb_a.tableData"]))
        self.assertIn("tableData", keys(self.widget("t1").get("dynamicPropertyPathList")))

    def test_theme_binding_keeps_the_colour_picker(self):
        self.use(seed_with({"widgetId": "b1", "widgetName": "bt_a", "type": "BUTTON_WIDGET"}))
        run(server.update_widgets([{"widget_id": "b1", "props": {"buttonColor": "{{appsmith.theme.colors.primaryColor}}"}}]))
        self.assertNotIn("buttonColor", keys(self.widget("b1").get("dynamicPropertyPathList")))

    def test_code_editor_property_is_not_marked_dynamic(self):
        self.use(seed_with({"widgetId": "x1", "widgetName": "txt_a", "type": "TEXT_WIDGET"}))
        run(server.update_widgets([{"widget_id": "x1", "props": {"text": "{{ q.data.length }}"}}]))
        self.assertNotIn("text", keys(self.widget("x1").get("dynamicPropertyPathList")))

    def test_add_widgets_registers_bindings_and_js_mode(self):
        self.use(seed_with())
        res = run(server.add_widgets([{"widget_type": "SWITCH_WIDGET", "new_id": "sw1",
                                       "props": {"defaultSwitchState": "{{ q.data[0].ativo }}"}}],
                                     allow_bindings=["sw1.defaultSwitchState"]))
        self.assertTrue(res[0].get("persisted"), res)
        w = self.widget("sw1")
        self.assertIn("defaultSwitchState", keys(w["dynamicBindingPathList"]))
        self.assertIn("defaultSwitchState", keys(w.get("dynamicPropertyPathList")))

    def test_add_select_bound_to_query_uses_the_dropdown_and_drops_sample_default(self):
        self.use(seed_with())
        run(server.add_widgets([{"widget_type": "SELECT_WIDGET", "new_id": "se1",
                                 "props": {"sourceData": "{{ q_filiais.data }}",
                                           "optionLabel": "FILIAL", "optionValue": "CODIGO_FILIAL"}}]))
        w = self.widget("se1")
        self.assertEqual(w["sourceData"], "{{q_filiais.data}}")
        self.assertIn("sourceData", keys(w["dynamicBindingPathList"]))
        self.assertNotIn("sourceData", keys(w.get("dynamicPropertyPathList")))
        self.assertEqual(w.get("defaultOptionValue"), "")

    def test_add_widgets_replaces_sample_data_but_merges_other_objects(self):
        seed = seed_with()
        seed["defaults"] = {"CHART_WIDGET": {
            "chartData": {"sample1": {"seriesName": "Sales", "data": [{"x": "a", "y": 1}]}},
            "customStyle": {"a": 1},
        }}
        self.use(seed)
        run(server.add_widgets([{"widget_type": "CHART_WIDGET", "new_id": "ch1", "props": {
            "chartData": {"s1": {"seriesName": "Total", "data": "{{ q.data }}"}},
            "customStyle": {"b": 2},
        }}]))
        w = self.widget("ch1")
        self.assertEqual(list(w["chartData"].keys()), ["s1"])
        self.assertIn("chartData.s1.data", keys(w["dynamicBindingPathList"]))
        self.assertEqual(w["customStyle"], {"a": 1, "b": 2})

    def test_custom_widget_event_handler_is_shown_as_code(self):
        self.use(seed_with({"widgetId": "c1", "widgetName": "cw_a", "type": "CUSTOM_WIDGET", "events": ["onSave"]}))
        run(server.update_custom_widget("c1", triggers={"onSave": "{{ q_salvar.run() }}"}))
        w = self.widget("c1")
        self.assertIn("onSave", keys(w["dynamicTriggerPathList"]))
        self.assertIn("onSave", keys(w.get("dynamicPropertyPathList")))


if __name__ == "__main__":
    unittest.main()
