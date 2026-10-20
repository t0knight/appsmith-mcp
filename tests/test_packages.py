"""Package tools: code (query/JS) and UI packages, publishing, and module instances on pages."""

import asyncio
import unittest

from appsmith_mcp import server
from tests.snippet_harness import FakeClient, root_widget

OK = {"responseMeta": {"success": True}}


def ok(data):
    return {**OK, "data": data}


PACKAGES = [
    {"id": "pk1", "name": "Querys Sistema", "type": "CODE", "lastPublishedAt": "2026-07-31", "workspaceId": "ws1"},
    {"id": "pk2", "name": "Elementos UI", "type": "UI", "workspaceId": "ws1",
     "gitArtifactMetadata": {"repoName": "Pack-Login"}},
]
PKG_DETAIL = ok({
    "packageData": PACKAGES[0],
    "modules": [
        {"id": "mq", "name": "q_filiais", "type": "QUERY_MODULE", "moduleUUID": "uq", "packageId": "pk1",
         "inputsForm": [{"id": "sec", "sectionName": "", "children": [
             {"id": "i1", "label": "limite", "propertyName": "inputs.limite", "controlType": "INPUT_TEXT", "defaultValue": "5"}]}]},
        {"id": "mj", "name": "securityJS", "type": "JS_MODULE", "moduleUUID": "uj", "packageId": "pk1",
         "inputsForm": [{"id": "sec2", "sectionName": "", "children": []}]},
    ],
})


def base_seed(responses, **extra):
    return {"widgets": {"0": root_widget()}, "responses": responses,
            "datasources": [{"id": "ds1", "pluginId": "mssql", "workspaceId": "ws1"}],
            "plugins": [{"id": "mssql", "packageName": "mssql-plugin", "type": "DB"}, {"id": "jsplg", "type": "JS"}],
            "ui": {"selectedWorkspace": {"workspace": {"id": "ws1"}},
                   "applications": {"currentApplication": {"id": "app1", "workspaceId": "ws1"}},
                   "editor": {"currentPageId": "p1", "loadingStates": {}}},
            **extra}


class PackageTests(unittest.TestCase):
    def use(self, s):
        self.client = FakeClient(s)
        server.client = self.client
        server.ready = True

    def calls(self, method, part):
        return [f for c in self.client.calls for f in c["fetches"] if f["method"] == method and part in f["url"]]

    def dispatched(self, type_):
        return [d for c in self.client.calls for d in c["dispatched"] if d["type"] == type_]

    # ---- packages & modules -------------------------------------------------------------
    def test_list_packages_uses_the_open_app_workspace(self):
        self.use(base_seed([{"match": "/api/v1/packages?workspaceId=ws1", "body": ok(PACKAGES)}]))
        out = asyncio.run(server.list_packages())
        self.assertEqual([(p["name"], p["type"], p["gitConnected"]) for p in out],
                         [("Querys Sistema", "CODE", False), ("Elementos UI", "UI", True)])

    def test_list_packages_without_context_lists_every_workspace(self):
        s = base_seed([{"match": "/api/v1/workspaces/home", "body": ok([{"id": "wa", "name": "A"}, {"id": "wb", "name": "B"}])},
                       {"match": "/api/v1/packages?workspaceId=wa", "body": ok(PACKAGES[:1])},
                       {"match": "/api/v1/packages?workspaceId=wb", "body": ok(PACKAGES[1:])}])
        s["ui"] = {"selectedWorkspace": {"workspace": {"id": "outro"}}, "applications": {"currentApplication": None},
                   "editor": {"loadingStates": {}}}
        self.use(s)
        out = asyncio.run(server.list_packages())
        self.assertEqual([(p["name"], p["workspaceName"]) for p in out], [("Querys Sistema", "A"), ("Elementos UI", "B")])

    def test_get_package_summarizes_modules(self):
        self.use(base_seed([{"match": "/api/v1/packages/pk1", "body": PKG_DETAIL}]))
        out = asyncio.run(server.get_package("pk1"))
        q = out["modules"][0]
        self.assertEqual((q["name"], q["type"]), ("q_filiais", "QUERY_MODULE"))
        self.assertEqual(q["inputs"], [{"name": "limite", "default": "5"}])
        self.assertTrue(q["editorUrl"].endswith("/pkg/pk1/mq/edit"))

    def test_open_module_waits_for_the_module_editor(self):
        s = base_seed([{"match": "/api/v1/packages/pk1", "body": PKG_DETAIL}])
        self.use(s)
        navigated = []

        async def fake_navigate(url):
            navigated.append(url)
        self.client.navigate = fake_navigate
        out = asyncio.run(server.open_module("pk1", "mq", timeout=1))
        self.assertTrue(navigated[0].endswith("/pkg/pk1/mq/edit"))
        self.assertIn("error", out)  # the fake editor never loads the module

        s["ui"]["editor"]["currentModuleId"] = "mq"
        s["moduleEntities"] = {"mq": {"id": "mq", "name": "q_filiais", "type": "QUERY_MODULE", "packageId": "pk1"}}
        self.use(s)
        self.client.navigate = fake_navigate
        out = asyncio.run(server.open_module("pk1", "mq", timeout=1))
        self.assertEqual(out["context"]["context"], "module")

    def test_create_code_package(self):
        self.use(base_seed([{"match": "/api/v1/packages?workspaceId=ws1", "method": "POST",
                             "body": ok({"id": "new", "name": "zz_code", "type": "CODE"})}]))
        out = asyncio.run(server.create_package("zz_code", "CODE"))
        self.assertEqual(out["id"], "new")
        self.assertEqual(self.calls("POST", "/api/v1/packages?workspaceId=ws1")[0]["body"]["type"], "CODE")

    def test_create_ui_package_brings_a_default_ui_module(self):
        self.use(base_seed([{"match": "/api/v1/packages/with-module", "method": "POST",
                             "body": ok({"id": "newui", "name": "zz_ui", "type": "UI"})}]))
        asyncio.run(server.create_package("zz_ui", "UI", module_name="zz_tela"))
        body = self.calls("POST", "/api/v1/packages/with-module")[0]["body"]
        self.assertEqual(body["packageData"]["name"], "zz_ui")
        mod = body["defaultModule"]
        self.assertEqual((mod["name"], mod["type"]), ("zz_tela", "UI_MODULE"))
        self.assertEqual(mod["layouts"][0]["dsl"]["children"][0]["type"], "MODULE_CONTAINER_WIDGET")

    def test_create_query_and_js_modules(self):
        # Works from the dashboard too: datasources/plugins come from the API, not the editor state.
        s = base_seed([
            {"match": "/api/v1/modules", "method": "POST", "body": ok({"id": "m9", "name": "x", "type": "QUERY_MODULE", "moduleUUID": "u9"})},
            {"match": "/api/v1/packages/pk1", "method": "GET", "body": PKG_DETAIL},
            {"match": "/api/v1/datasources?workspaceId=ws1", "body": ok([{"id": "ds1", "name": "APPS", "pluginId": "mssql", "workspaceId": "ws1"}])},
            {"match": "/api/v1/plugins?workspaceId=ws1", "body": ok([{"id": "mssql", "type": "DB"}, {"id": "jsplg", "type": "JS"}])},
        ])
        s["datasources"], s["plugins"] = [], []
        self.use(s)
        asyncio.run(server.create_modules("pk1", [
            {"type": "QUERY", "name": "q_top", "datasource_id": "APPS", "body": "SELECT TOP {{inputs.limite}} * FROM T",
             "inputs": [{"name": "limite", "default": "10"}]},
            {"type": "JS", "name": "utilJS", "body": "export default {\n  soma (a, b) { return a + b }\n}"},
        ]))
        q, j = [c["body"] for c in self.calls("POST", "/api/v1/modules")]
        self.assertEqual((q["type"], q["entity"]["type"], q["entity"]["pluginId"]), ("QUERY_MODULE", "ACTION", "mssql"))
        self.assertEqual(q["entity"]["dynamicBindingPathList"], [{"key": "body"}])
        self.assertEqual(q["inputsForm"][0]["children"][0]["propertyName"], "inputs.limite")
        self.assertEqual((j["type"], j["entity"]["type"], [a["name"] for a in j["entity"]["actions"]]),
                         ("JS_MODULE", "JS_OBJECT", ["soma"]))
        self.assertEqual((j["entity"]["pluginId"], j["entity"]["workspaceId"]), ("jsplg", "ws1"))

    def test_update_module_inputs_keep_ids_and_rename_uses_refactor(self):
        self.use(base_seed([
            {"match": "/api/v1/modules/mq", "method": "GET", "body": ok(PKG_DETAIL["data"]["modules"][0])},
            {"match": "/api/v1/modules/mq", "method": "PUT", "body": ok({})},
            {"match": "/api/v1/modules/refactor", "method": "PUT", "body": ok({"name": "q_novo"})},
        ]))
        asyncio.run(server.update_module("mq", name="q_novo",
                                         inputs=[{"name": "limite", "default": "20"}, {"name": "filial", "default": ""}]))
        put = self.calls("PUT", "/api/v1/modules/mq")[0]["body"]
        kids = put["inputsForm"][0]["children"]
        self.assertEqual([(k["id"] == "i1", k["label"], k["defaultValue"]) for k in kids],
                         [(True, "limite", "20"), (False, "filial", "")])
        self.assertEqual(self.calls("PUT", "/api/v1/modules/refactor")[0]["body"],
                         {"moduleId": "mq", "oldName": "q_filiais", "newName": "q_novo"})

    def test_ui_module_outputs_register_bindings(self):
        ui = {"id": "mu", "name": "filtro", "type": "UI_MODULE", "packageId": "pk2",
              "inputsForm": [{"id": "s", "sectionName": "", "children": []}],
              "outputsForm": [{"id": "o", "sectionName": "", "children": []}], "layouts": [{"id": "l"}]}
        self.use(base_seed([{"match": "/api/v1/modules/mu", "method": "GET", "body": ok(ui)},
                            {"match": "/api/v1/modules/mu", "method": "PUT", "body": ok({})}]))
        asyncio.run(server.update_module("mu", outputs=[{"name": "produtos", "value": "{{sel_produto.selectedOptionValues}}"}]))
        put = self.calls("PUT", "/api/v1/modules/mu")[0]["body"]
        self.assertNotIn("layouts", put)
        self.assertEqual(put["outputsForm"][0]["children"][0]["propertyName"], "outputs.produtos")
        self.assertEqual(put["dynamicBindingPathList"], [{"key": "outputsForm[0].children[0].value"}])

    def test_publish_requires_confirmation(self):
        self.use(base_seed([{"match": "/api/v1/packages/pk2", "method": "GET", "body": ok({"packageData": PACKAGES[1], "modules": []})}]))
        out = asyncio.run(server.publish_package("pk2"))
        self.assertIn("error", out)
        self.assertEqual(self.calls("POST", "/publish"), [])

    def test_publish_with_confirmation_warns_about_git(self):
        self.use(base_seed([
            {"match": "/api/v1/packages/pk2", "method": "GET", "body": ok({"packageData": PACKAGES[1], "modules": []})},
            {"match": "/api/v1/packages/pk2/publish", "method": "POST", "body": ok({"status": True, "lastPublishedVersion": "0.0.3"})},
        ]))
        out = asyncio.run(server.publish_package("pk2", confirm=True))
        self.assertEqual(out["lastPublishedVersion"], "0.0.3")
        self.assertIn("Git", out["warning"])
        self.assertEqual(self.calls("POST", "/api/v1/packages/pk2/publish")[0]["body"], {})

    # ---- module instances on pages -----------------------------------------------------
    CONSUMABLES = ok({"packages": [{"id": "pp1", "name": "Querys Sistema"}], "modules": [
        {"id": "pub_q", "originModuleId": "mq", "name": "q_filiais", "type": "QUERY_MODULE", "moduleUUID": "uq", "packageId": "pp1"},
        {"id": "pub_u", "originModuleId": "mu", "name": "filtro", "type": "UI_MODULE", "moduleUUID": "uu", "packageId": "pp2"},
    ]})
    INSTANCES = ok([
        {"id": "inst1", "name": "filiais", "type": "QUERY_MODULE", "moduleUUID": "uq", "sourceModuleId": "pub_q",
         "inputs": {"limite": "5"}, "layouts": [{"dsl": {}}]},
        {"id": "inst2", "name": "filtro1", "type": "UI_MODULE", "moduleUUID": "uu", "sourceModuleId": "pub_u", "inputs": {}},
    ])

    def instance_seed(self, extra=()):
        return base_seed([
            {"match": "/api/v1/packages/consumables", "body": self.CONSUMABLES},
            {"match": "/api/v1/moduleInstances?contextId=p1", "method": "GET", "body": self.INSTANCES},
            {"match": "/api/v1/moduleInstances", "method": "POST", "body": ok({"moduleInstance": {"id": "inst9", "name": "q_fil", "type": "QUERY_MODULE", "inputs": {"limite": "5"}}})},
            {"match": "/api/v1/moduleInstances/", "method": "PUT", "body": ok({"inputs": {}})},
            {"match": "/api/v1/packages/app1/poll-pull-status", "body": ok("UPGRADABLE")},
            *extra,
        ])

    def test_list_module_instances(self):
        self.use(self.instance_seed())
        out = asyncio.run(server.list_module_instances())
        self.assertEqual([(i["name"], i["module"], i["type"]) for i in out["instances"]],
                         [("filiais", "q_filiais", "QUERY_MODULE"), ("filtro1", "filtro", "UI_MODULE")])
        self.assertEqual(out["packageUpdates"], "UPGRADABLE")

    def test_add_query_module_instance_with_inputs(self):
        self.use(self.instance_seed())
        res = asyncio.run(server.add_module_instances([{"module": "q_filiais", "name": "q_fil", "inputs": {"limite": "{{sel_qtd.selectedOptionValue}}"}}]))
        self.assertEqual(res[0]["id"], "inst9")
        post = self.calls("POST", "/api/v1/moduleInstances")[0]["body"]
        self.assertEqual(post, {"sourceModuleId": "pub_q", "contextId": "p1", "contextType": "PAGE", "name": "q_fil"})
        put = self.calls("PUT", "/api/v1/moduleInstances/inst9")[0]["body"]
        self.assertEqual(put["inputs"], {"limite": "{{sel_qtd.selectedOptionValue}}"})
        self.assertTrue(self.dispatched("SETUP_MODULE_INSTANCE_INIT"))

    def test_add_ui_module_instance_drops_the_module_widget(self):
        self.use(self.instance_seed())
        res = asyncio.run(server.add_module_instances([{"module": "filtro", "name": "filtro1", "top": 2, "rows": 12}]))
        add = self.dispatched("WIDGET_ADD_CHILD")[0]["payload"]
        self.assertEqual((add["type"], add["widgetName"], add["widgetId"], add["topRow"]), ("MODULE_WIDGET_uu", "filtro1", "0", 2))
        self.assertEqual(res[0]["id"], "inst2")
        self.assertEqual(self.calls("POST", "/api/v1/moduleInstances"), [])

    def test_update_module_instance_merges_inputs(self):
        self.use(self.instance_seed())
        asyncio.run(server.update_module_instances([{"instance": "filiais", "inputs": {"filial": "{{appsmith.store.filial}}"}}]))
        put = self.calls("PUT", "/api/v1/moduleInstances/inst1")[0]["body"]
        self.assertEqual(put["inputs"], {"limite": "5", "filial": "{{appsmith.store.filial}}"})
        self.assertNotIn("layouts", put)

    def test_update_app_packages_pulls_when_upgradable(self):
        self.use(base_seed([
            {"match": "/api/v1/packages/app1/poll-pull-status", "bodies": [ok("UPGRADABLE"), ok("UPGRADED")]},
            {"match": "/api/v1/packages/app1/pull", "method": "POST", "body": ok({"moduleInstances": [{"id": "a"}, {"id": "b"}]})},
        ]))
        out = asyncio.run(server.update_app_packages())
        self.assertEqual(self.calls("POST", "/api/v1/packages/app1/pull")[0]["url"], "/api/v1/packages/app1/pull?requestPageId=p1")
        self.assertEqual((out["before"], out["after"], out["instancesUpdated"]), ("UPGRADABLE", "UPGRADED", 2))

    def test_update_app_packages_is_a_noop_when_up_to_date(self):
        self.use(base_seed([{"match": "/api/v1/packages/app1/poll-pull-status", "body": ok("UPGRADED")}]))
        out = asyncio.run(server.update_app_packages())
        self.assertTrue(out["upToDate"])
        self.assertEqual(self.calls("POST", "/pull"), [])


if __name__ == "__main__":
    unittest.main()


class PackageDeletionTests(PackageTests):
    """Deleting is irreversible and breaks every app holding an instance, so it is gated."""

    def test_delete_package_requires_confirmation(self):
        self.use(base_seed([{"match": "/api/v1/packages/pk1", "body": PKG_DETAIL}]))
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(server.delete_packages(["pk1"]))
        self.assertIn("confirm", str(ctx.exception))
        self.assertEqual(self.calls("DELETE", "/api/v1/packages/"), [])

    def test_delete_package_with_confirmation(self):
        self.use(base_seed([{"match": "/api/v1/packages/pk1", "method": "DELETE", "body": ok({"id": "pk1"})}]))
        result = asyncio.run(server.delete_packages(["pk1"], confirm=True))
        self.assertTrue(result[0]["ok"], result)
        self.assertEqual(len(self.calls("DELETE", "/api/v1/packages/pk1")), 1)

    def test_delete_modules_requires_confirmation(self):
        self.use(base_seed([]))
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(server.delete_modules(["mq"]))
        self.assertIn("confirm", str(ctx.exception))

    def test_delete_modules_with_confirmation(self):
        self.use(base_seed([{"match": "/api/v1/modules/mq", "method": "DELETE", "body": ok({"id": "mq"})}]))
        result = asyncio.run(server.delete_modules(["mq"], confirm=True))
        self.assertTrue(result[0]["ok"], result)
        self.assertEqual(len(self.calls("DELETE", "/api/v1/modules/mq")), 1)
