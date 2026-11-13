"""Run behaviour (Manual / Automatic / On page load) for queries and JS functions."""

import asyncio
import unittest

from appsmith_mcp import server
from tests.snippet_harness import FakeClient, root_widget

ACTIONS = [{"config": {"id": "q1", "name": "q_itens", "pageId": "p1", "runBehaviour": "MANUAL"}}]
JS = [{"config": {"id": "c1", "name": "utilJS", "pageId": "p1", "actions": [
    {"id": "f1", "name": "carregar", "runBehaviour": "MANUAL"},
    {"id": "f2", "name": "recalcular", "runBehaviour": "AUTOMATIC"},
]}}]


def seed(**extra):
    return {"widgets": {"0": root_widget()}, "actions": ACTIONS, "jsActions": JS,
            "responses": [
                {"match": "/api/v1/actions/runBehaviour/", "method": "PUT",
                 "body": {"responseMeta": {"success": True}, "data": {"runBehaviour": "ON_PAGE_LOAD"}}},
                {"match": "/api/v1/pages/p1", "method": "GET",
                 "body": {"responseMeta": {"success": True}, "data": {"layouts": [{"layoutOnLoadActions": [[{"id": "q1", "name": "q_itens"}]]}]}}},
            ], **extra}


class RunBehaviourTests(unittest.TestCase):
    def use(self, s):
        self.client = FakeClient(s)
        server.client = self.client
        server.ready = True

    def puts(self):
        return [f["url"] for c in self.client.calls for f in c["fetches"] if f["method"] == "PUT"]

    def test_query_and_js_function_use_the_run_behaviour_endpoint(self):
        self.use(seed())
        res = asyncio.run(server.set_run_behaviour([
            {"query": "q_itens", "behaviour": "ON_PAGE_LOAD"},
            {"js_object": "utilJS", "function": "carregar", "behaviour": "MANUAL"},
        ]))
        self.assertEqual(self.puts(), ["/api/v1/actions/runBehaviour/q1?behaviour=ON_PAGE_LOAD",
                                       "/api/v1/actions/runBehaviour/f1?behaviour=MANUAL"])
        self.assertEqual([r.get("target") for r in res["results"]], ["q_itens", "utilJS.carregar"])
        self.assertEqual(res["onLoad"], [{"id": "q1", "name": "q_itens"}])

    def test_automatic_needs_a_reason(self):
        self.use(seed())
        res = asyncio.run(server.set_run_behaviour([{"query": "q_itens", "behaviour": "AUTOMATIC"}]))
        self.assertIn("error", res["results"][0])
        self.assertEqual(self.puts(), [])

    def test_automatic_with_reason_is_applied_and_reported(self):
        self.use(seed())
        res = asyncio.run(server.set_run_behaviour([{"query": "q_itens", "behaviour": "AUTOMATIC",
                                                    "reason": "recalcula quando o filtro muda"}]))
        self.assertEqual(self.puts(), ["/api/v1/actions/runBehaviour/q1?behaviour=AUTOMATIC"])
        self.assertEqual(res["results"][0]["reason"], "recalcula quando o filtro muda")

    def test_unknown_behaviour_is_rejected(self):
        self.use(seed())
        res = asyncio.run(server.set_run_behaviour([{"query": "q_itens", "behaviour": "ON_LOAD"}]))
        self.assertIn("error", res["results"][0])

    def test_listings_show_run_behaviour(self):
        self.use(seed())
        qs = asyncio.run(server.list_queries())
        self.assertEqual(qs[0]["runBehaviour"], "MANUAL")
        js = asyncio.run(server.list_js_objects())
        self.assertEqual(js[0]["actions"][1]["runBehaviour"], "AUTOMATIC")

    def test_lint_flags_automatic_entities(self):
        self.use(seed())
        out = asyncio.run(server.lint_design())
        hits = [(f["rule"], f["widget"]) for f in out["findings"] if f["rule"] == "automatic_run_behaviour"]
        self.assertEqual(hits, [("automatic_run_behaviour", "utilJS.recalcular")])


if __name__ == "__main__":
    unittest.main()
