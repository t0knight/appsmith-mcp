"""Existing tools must work inside a package module editor (/pkg or /ui-pkg ... /edit)."""

import asyncio
import unittest

from appsmith_mcp import server
from tests.snippet_harness import FakeClient, find_node, keys, root_widget

MOD, PKG, LAYOUT = "m1", "p1pkg", "lay1"


def module_seed(**extra):
    container = {"widgetId": "module-container-0", "widgetName": "ModuleContainer", "type": "MODULE_CONTAINER_WIDGET",
                 "parentId": "0", "children": ["module-canvas-0"],
                 "inputsForm": [{"id": "s", "children": []}], "outputsForm": [], "onInputChangeConfig": {},
                 "dynamicTriggerPathList": None, "dynamicBindingPathList": []}
    canvas = {"widgetId": "module-canvas-0", "widgetName": "ModuleContainerCanvas", "type": "CANVAS_WIDGET",
              "parentId": "module-container-0", "children": ["t1"], "dynamicBindingPathList": []}
    text = {"widgetId": "t1", "widgetName": "txt_a", "type": "TEXT_WIDGET", "parentId": "module-canvas-0",
            "dynamicBindingPathList": [], "dynamicTriggerPathList": []}
    root = root_widget(["module-container-0"])
    seed = {
        "widgets": {"0": root, "module-container-0": container, "module-canvas-0": canvas, "t1": text},
        "url": f"http://appsmith/ui-pkg/{PKG}/{MOD}/edit",
        "ui": {
            "editor": {"currentPageId": None, "currentModuleId": MOD, "currentPackageId": PKG, "loadingStates": {}},
            "applications": {"currentApplication": None},
            "selectedWorkspace": {"workspace": {"id": "ws1"}},
        },
        "moduleEntities": {MOD: {"id": MOD, "packageId": PKG, "name": "mod_a", "type": "UI_MODULE",
                                 "layouts": [{"id": LAYOUT}]}},
        "datasources": [{"id": "ds1", "pluginId": "plg", "workspaceId": "ws1"}],
        "plugins": [{"id": "plg", "packageName": "mssql-plugin", "type": "DB"}, {"id": "jsplg", "type": "JS"}],
        "responses": [
            {"match": "/api/v1/actions", "method": "POST", "body": {"responseMeta": {"success": True}, "data": {"id": "a9", "name": "q_mod"}}},
            {"match": "/api/v1/collections/actions", "method": "POST", "body": {"responseMeta": {"success": True}, "data": {"id": "j9", "name": "js_mod", "actions": [{"name": "ola"}]}}},
        ],
    }
    seed.update(extra)
    return seed


class ModuleContextTests(unittest.TestCase):
    def use(self, seed):
        self.client = FakeClient(seed)
        server.client = self.client
        server.ready = True

    def fetches(self, method, part):
        return [f for c in self.client.calls for f in c["fetches"] if f["method"] == method and part in f["url"]]

    def test_widget_writes_are_saved_by_the_module_editor(self):
        # In a module the editor re-initialises the canvas from its own saves, so the MCP hands
        # the change to the editor (UPDATE_LAYOUT) and waits for the module save to land.
        self.use(module_seed())
        res = asyncio.run(server.update_widgets([{"widget_id": "t1", "props": {"text": "Oi"}}]))
        self.assertTrue(res[0].get("persisted"), res)
        layout = [d for c in self.client.calls for d in c["dispatched"] if d["type"] == "UPDATE_LAYOUT"]
        self.assertEqual(layout[-1]["payload"]["widgets"]["t1"]["text"], "Oi")
        puts = self.fetches("PUT", "/api/v1/layouts/")
        self.assertEqual(puts[-1]["url"], f"/api/v1/layouts/{LAYOUT}/modules/{MOD}?packageId={PKG}")
        self.assertEqual(find_node(puts[-1]["body"]["dsl"], "t1")["text"], "Oi")

    def test_removed_widgets_leave_the_module_layout(self):
        self.use(module_seed())
        res = asyncio.run(server.delete_widgets(["t1"]))
        self.assertTrue(res[0].get("persisted"), res)
        dsl = self.fetches("PUT", "/api/v1/layouts/")[-1]["body"]["dsl"]
        self.assertIsNone(find_node(dsl, "t1"))
        self.assertEqual(find_node(dsl, "module-canvas-0")["children"], [])

    def test_unconfirmed_module_save_is_an_error(self):
        self.use(module_seed(editorSaves=False))
        res = asyncio.run(server.update_widgets([{"widget_id": "t1", "props": {"text": "Oi"}}]))
        self.assertNotIn("persisted", res[0])
        self.assertIn("module editor", res[0]["error"])

    def test_build_context_reports_the_module(self):
        self.use(module_seed())
        ctx = asyncio.run(server.get_build_context())
        self.assertEqual(ctx["context"], "module")
        self.assertEqual((ctx["moduleId"], ctx["packageId"]), (MOD, PKG))
        self.assertTrue(ctx["consistent"])
        self.assertTrue(ctx["ready"])

    def test_create_queries_targets_the_module(self):
        self.use(module_seed())
        res = asyncio.run(server.create_queries([{"name": "q_mod", "datasource_id": "ds1",
                                                  "action_config": {"body": "SELECT 1"}}]))
        self.assertEqual(res[0]["id"], "a9")
        body = self.fetches("POST", "/api/v1/actions")[-1]["body"]
        self.assertEqual((body["moduleId"], body["contextType"]), (MOD, "MODULE"))
        self.assertNotIn("pageId", body)
        refetch = [d for c in self.client.calls for d in c["dispatched"] if d["type"] == "FETCH_MODULE_ENTITIES_INIT"]
        self.assertEqual(refetch[-1]["payload"], {"moduleId": MOD})

    def test_page_load_actions_recompute_the_module_layout(self):
        seed = module_seed(actions=[{"config": {"id": "a1", "name": "q_mod", "moduleId": MOD}}])
        seed["responses"] = [
            {"match": "/api/v1/actions/a1", "method": "PUT", "body": {"responseMeta": {"success": True}, "data": {"name": "q_mod", "runBehaviour": "ON_PAGE_LOAD"}}},
            {"match": f"/api/v1/modules/{MOD}", "method": "GET", "body": {"responseMeta": {"success": True}, "data": {"layouts": [{"layoutOnLoadActions": [[{"id": "a1", "name": "q_mod"}]]}]}}},
        ]
        self.use(seed)
        res = asyncio.run(server.set_page_load_actions(["a1"]))
        self.assertTrue(res["layoutRecomputed"], res)
        self.assertEqual(res["layoutOnLoadActions"], [{"id": "a1", "name": "q_mod"}])
        self.assertIn(f"/modules/{MOD}", self.fetches("PUT", "/api/v1/layouts/")[-1]["url"])

    def test_create_js_objects_targets_the_module(self):
        self.use(module_seed())
        res = asyncio.run(server.create_js_objects([{"name": "js_mod", "body": "export default {\n  ola () { return 1 }\n}"}]))
        self.assertEqual(res[0]["id"], "j9")
        body = self.fetches("POST", "/api/v1/collections/actions")[-1]["body"]
        self.assertEqual((body["moduleId"], body["contextType"], body["name"]), (MOD, "MODULE", "js_mod"))
        self.assertEqual([a["name"] for a in body["actions"]], ["ola"])


if __name__ == "__main__":
    unittest.main()
