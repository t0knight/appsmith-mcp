"""Every widget configuration must stay visible in the Appsmith property pane.

A property whose pane control is visual (switch, dropdown, colour picker, data selector)
cannot render `{{ }}` code in that control: the maintainer sees an empty or wrong-looking
field while the real value hides in the DSL. These tests pin the classification that decides
which writes are refused, and the three binding shapes that ARE the native control.
"""

import asyncio
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from appsmith_mcp import server  # noqa: E402
from tests.snippet_harness import FakeClient, keys, root_widget  # noqa: E402

from appsmith_mcp.panel_policy import (  # noqa: E402
    FREE,
    HIDDEN_BINDING,
    LITERAL,
    NATIVE_BINDING,
    classify_value,
    validate_panel_writes,
)

CONTROLS = {
    "SELECT_WIDGET": {
        "isVisible": "SWITCH",
        "sourceData": "ONE_CLICK_BINDING_CONTROL",
        "accentColor": "COLOR_PICKER",
    },
    "TABLE_WIDGET_V2": {
        "isVisible": "SWITCH",
        "tableData": "ONE_CLICK_BINDING_CONTROL",
    },
}


class ClassifyTests(unittest.TestCase):
    def test_literal_is_the_target(self):
        self.assertEqual(classify_value("SELECT_WIDGET", "isVisible", True, CONTROLS), LITERAL)
        self.assertEqual(classify_value("SELECT_WIDGET", "accentColor", "#800020", CONTROLS), LITERAL)

    def test_prop_without_visual_control_is_free(self):
        # onClick / placeholderText are code fields in the pane: nothing visual to hide.
        self.assertEqual(classify_value("SELECT_WIDGET", "onClick", "{{ q.run() }}", CONTROLS), FREE)
        self.assertEqual(classify_value("SELECT_WIDGET", "placeholderText", "{{ x }}", CONTROLS), FREE)

    def test_native_bindings_are_allowed(self):
        self.assertEqual(
            classify_value("TABLE_WIDGET_V2", "tableData", "{{q_lojas.data}}", CONTROLS),
            NATIVE_BINDING,
        )
        self.assertEqual(
            classify_value("TABLE_WIDGET_V2", "tableData", "{{ q_lojas.data }}", CONTROLS),
            NATIVE_BINDING,
        )
        self.assertEqual(
            classify_value(
                "SELECT_WIDGET", "accentColor", "{{appsmith.theme.colors.primaryColor}}", CONTROLS
            ),
            NATIVE_BINDING,
        )

    def test_column_props_that_are_native_by_nature(self):
        for prop, value in (
            ("computedValue", "{{ currentRow.nome }}"),
            ("validation", "{{ editedValue.length > 2 }}"),
            ("buttonColor", "{{ currentRow.banido ? '#16A34A' : '#D97706' }}"),
            ("isDisabled", "{{ currentRow.bloqueado }}"),
        ):
            with self.subTest(prop=prop):
                self.assertEqual(
                    classify_value("TABLE_WIDGET_V2", prop, value, CONTROLS, column_prop=True),
                    NATIVE_BINDING,
                )

    def test_binding_on_visual_control_is_hidden(self):
        self.assertEqual(
            classify_value("SELECT_WIDGET", "isVisible", "{{ chk.isChecked }}", CONTROLS),
            HIDDEN_BINDING,
        )
        # A transforming expression hides the query from the Data dropdown too.
        self.assertEqual(
            classify_value("TABLE_WIDGET_V2", "tableData", "{{ q.data.filter(r => r.ok) }}", CONTROLS),
            HIDDEN_BINDING,
        )

    def test_column_isvisible_without_row_scope_is_still_hidden(self):
        self.assertEqual(
            classify_value("TABLE_WIDGET_V2", "isVisible", "{{ chk.isChecked }}", CONTROLS, column_prop=True),
            HIDDEN_BINDING,
        )


class ValidateTests(unittest.TestCase):
    def entry(self, **props):
        return [{"label": "sel_a", "type": "SELECT_WIDGET", "props": props}]

    def test_hidden_binding_becomes_a_problem(self):
        problems, authorized = validate_panel_writes(
            self.entry(isVisible="{{ chk.isChecked }}"), CONTROLS
        )
        self.assertEqual(authorized, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("isVisible", problems[0])
        self.assertIn("SWITCH", problems[0])
        self.assertIn("allow_bindings", problems[0])

    def test_one_click_problem_points_at_connect_widget_data(self):
        problems, _ = validate_panel_writes(
            [{"label": "tbl", "type": "TABLE_WIDGET_V2",
              "props": {"tableData": "{{ q.data.filter(r => r.ok) }}"}}],
            CONTROLS,
        )
        self.assertIn("connect_widget_data", problems[0])

    def test_authorized_path_passes_and_is_reported(self):
        problems, authorized = validate_panel_writes(
            self.entry(isVisible="{{ chk.isChecked }}"),
            CONTROLS,
            allow_bindings=["sel_a.isVisible"],
        )
        self.assertEqual(problems, [])
        self.assertEqual(authorized, ["sel_a.isVisible"])

    def test_authorization_is_per_path_not_global(self):
        problems, _ = validate_panel_writes(
            self.entry(isVisible="{{ a }}", accentColor="{{ b }}"),
            CONTROLS,
            allow_bindings=["sel_a.isVisible"],
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("accentColor", problems[0])

    def test_literals_produce_nothing(self):
        problems, authorized = validate_panel_writes(self.entry(isVisible=True), CONTROLS)
        self.assertEqual((problems, authorized), ([], []))

    def test_unknown_widget_type_is_left_alone(self):
        problems, _ = validate_panel_writes(
            [{"label": "x", "type": "WIDGET_FROM_THE_FUTURE", "props": {"isVisible": "{{ a }}"}}],
            CONTROLS,
        )
        self.assertEqual(problems, [])


class WriteGuardTests(unittest.TestCase):
    """The classification above, enforced by the tools that actually write."""

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

    def select(self):
        self.use({"widgetId": "s1", "widgetName": "sel_a", "type": "SELECT_WIDGET"})

    def test_update_refuses_hidden_binding_and_writes_nothing(self):
        self.select()
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(
                server.update_widgets(
                    [{"widget_id": "s1", "props": {"isVisible": "{{ chk.isChecked }}"}}]
                )
            )
        self.assertIn("isVisible", str(ctx.exception))
        self.assertIn("allow_bindings", str(ctx.exception))
        self.assertNotIn(
            "isVisible", keys(self.client.last["widgets"]["s1"].get("dynamicBindingPathList"))
        )

    def test_update_authorized_binding_turns_on_js_toggle(self):
        self.select()
        asyncio.run(
            server.update_widgets(
                [{"widget_id": "s1", "props": {"isVisible": "{{ chk.isChecked }}"}}],
                allow_bindings=["sel_a.isVisible"],
            )
        )
        w = self.client.last["widgets"]["s1"]
        self.assertIn("isVisible", keys(w["dynamicBindingPathList"]))
        self.assertIn("isVisible", keys(w.get("dynamicPropertyPathList")))

    def test_update_literal_still_writes(self):
        self.select()
        asyncio.run(server.update_widgets([{"widget_id": "s1", "props": {"isVisible": False}}]))
        self.assertIs(self.client.last["widgets"]["s1"]["isVisible"], False)

    def test_add_refuses_hidden_binding_on_new_widget(self):
        self.use()
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(
                server.add_widgets(
                    [
                        {
                            "widget_type": "SELECT_WIDGET",
                            "name": "sel_novo",
                            "props": {"isVisible": "{{ chk.isChecked }}"},
                        }
                    ]
                )
            )
        self.assertIn("isVisible", str(ctx.exception))
        self.assertIn("sel_novo.isVisible", str(ctx.exception))

    def test_add_allows_query_data_on_new_table(self):
        self.use()
        asyncio.run(
            server.add_widgets(
                [
                    {
                        "widget_type": "TABLE_WIDGET_V2",
                        "name": "tbl",
                        "props": {"tableData": "{{q_lojas.data}}"},
                    }
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
