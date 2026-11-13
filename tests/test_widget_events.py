"""Event handlers must land in the shape the property pane's action selector understands.

The pane shows its dropdown (Execute a query / Show alert / Navigate to ...) only while the
handler is a single recognised call. A chain or a hand-written expression still works, but the
pane falls back to raw code — so the builder is told which of the two they got.
"""

import asyncio
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from appsmith_mcp.widget_events import build_action  # noqa: E402
from appsmith_mcp import server  # noqa: E402
from tests.snippet_harness import FakeClient, keys, root_widget  # noqa: E402


class BuildActionTests(unittest.TestCase):
    def test_run_query_is_native(self):
        self.assertEqual(
            build_action({"action": "run_query", "query": "q_salvar"}),
            ("{{ q_salvar.run() }}", True),
        )

    def test_run_js_function(self):
        self.assertEqual(
            build_action({"action": "run_js", "object": "UtilsJS", "function": "recarregar"})[0],
            "{{ UtilsJS.recarregar() }}",
        )

    def test_show_alert_with_and_without_style(self):
        code, native = build_action(
            {"action": "show_alert", "message": "Salvo com sucesso", "style": "success"}
        )
        self.assertEqual(code, "{{ showAlert('Salvo com sucesso', 'success') }}")
        self.assertTrue(native)
        self.assertEqual(
            build_action({"action": "show_alert", "message": "Pronto"})[0],
            "{{ showAlert('Pronto') }}",
        )

    def test_apostrophe_in_message_is_escaped(self):
        code, _ = build_action({"action": "show_alert", "message": "Cliente d'Ávila"})
        self.assertEqual(code, "{{ showAlert('Cliente d\\'Ávila') }}")

    def test_navigate_to_page_with_params(self):
        self.assertEqual(
            build_action({"action": "navigate_to", "page": "lojas"})[0],
            "{{ navigateTo('lojas', {}, 'SAME_WINDOW') }}",
        )
        self.assertEqual(
            build_action({"action": "navigate_to", "page": "loja", "params": {"id": 7}})[0],
            '{{ navigateTo(\'loja\', {"id": 7}, \'SAME_WINDOW\') }}',
        )

    def test_store_value_and_clear_store(self):
        self.assertEqual(
            build_action({"action": "store_value", "key": "aba", "value": "resumo"})[0],
            "{{ storeValue('aba', 'resumo') }}",
        )
        self.assertEqual(build_action({"action": "clear_store"})[0], "{{ clearStore() }}")

    def test_modal_actions(self):
        self.assertEqual(
            build_action({"action": "show_modal", "modal": "mdl_item"})[0],
            "{{ showModal('mdl_item') }}",
        )
        self.assertEqual(
            build_action({"action": "close_modal", "modal": "mdl_item"})[0],
            "{{ closeModal('mdl_item') }}",
        )

    def test_reset_widget_and_copy(self):
        self.assertEqual(
            build_action({"action": "reset_widget", "widget": "frm_item"})[0],
            "{{ resetWidget('frm_item', true) }}",
        )
        self.assertEqual(
            build_action({"action": "copy_to_clipboard", "text": "abc"})[0],
            "{{ copyToClipboard('abc') }}",
        )

    def test_callback_is_accepted_but_not_native(self):
        code, native = build_action(
            {
                "action": "run_query",
                "query": "q_salvar",
                "on_success": {"action": "show_alert", "message": "ok"},
            }
        )
        self.assertEqual(code, "{{ q_salvar.run().then(() => showAlert('ok')) }}")
        self.assertFalse(native)

    def test_failure_callback(self):
        code, native = build_action(
            {
                "action": "run_query",
                "query": "q_salvar",
                "on_failure": {"action": "show_alert", "message": "erro", "style": "error"},
            }
        )
        self.assertIn(".catch(() => showAlert('erro', 'error'))", code)
        self.assertFalse(native)

    def test_raw_code_is_accepted_but_not_native(self):
        self.assertEqual(
            build_action({"code": "{{ q.run().then(() => x()) }}"}),
            ("{{ q.run().then(() => x()) }}", False),
        )

    def test_unknown_action_is_rejected_with_the_supported_list(self):
        with self.assertRaises(ValueError) as ctx:
            build_action({"action": "faz_magica"})
        self.assertIn("run_query", str(ctx.exception))

    def test_missing_required_field_is_rejected_clearly(self):
        with self.assertRaises(ValueError) as ctx:
            build_action({"action": "run_query"})
        self.assertIn("query", str(ctx.exception))



class SetWidgetEventsToolTests(unittest.TestCase):
    """The tool writes through update_widgets, so the handler lands as a trigger."""

    def use(self, *widgets):
        ws = {"0": root_widget([w["widgetId"] for w in widgets])}
        for w in widgets:
            ws[w["widgetId"]] = {"parentId": "0", "dynamicBindingPathList": [],
                                 "dynamicTriggerPathList": [], **w}
        seed = {"widgets": ws, "actions": [],
                "defaults": {t: s.get("defaults", {}) for t, s in server.WIDGET_PROPS.items()}}
        self.client = FakeClient(seed)
        server.client = self.client
        server.ready = True

    def test_onclick_is_registered_as_a_trigger(self):
        self.use({"widgetId": "b1", "widgetName": "bt_salvar", "type": "BUTTON_WIDGET"})
        report = asyncio.run(server.set_widget_events([
            {"widget": "b1", "events": {"onClick": {"action": "run_query", "query": "q_salvar"}}}
        ]))
        self.assertEqual(report[0]["native"], True)
        w = self.client.last["widgets"]["b1"]
        self.assertEqual(w["onClick"], "{{ q_salvar.run() }}")
        self.assertIn("onClick", keys(w["dynamicTriggerPathList"]))

    def test_chained_handler_reports_not_native(self):
        self.use({"widgetId": "b1", "widgetName": "bt_salvar", "type": "BUTTON_WIDGET"})
        report = asyncio.run(server.set_widget_events([
            {"widget": "b1", "events": {"onClick": {
                "action": "run_query", "query": "q_salvar",
                "on_success": {"action": "show_alert", "message": "ok"}}}}
        ]))
        self.assertFalse(report[0]["native"])


if __name__ == "__main__":
    unittest.main()
