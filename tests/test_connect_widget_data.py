"""connect_widget_data must leave the widget as if someone picked the query in the Data dropdown."""

import asyncio
import unittest

from appsmith_mcp import server
from tests.snippet_harness import FakeClient, find_node, keys, root_widget

ROWS = [
    {"id": 1, "nome_filial": "JK", "valor_total": 10.5, "criado_em": "2026-01-01T10:00:00Z", "ativo": True},
    {"id": 2, "nome_filial": "BH", "valor_total": 7, "criado_em": "2026-01-02T11:00:00Z", "ativo": False},
]


def seed(widget, rows=ROWS):
    action = {"config": {"id": "q1", "name": "q_itens", "pageId": "p1"}, "isLoading": False,
              "data": {"body": rows} if rows is not None else None}
    return {
        "widgets": {"0": root_widget([widget["widgetId"]]),
                    widget["widgetId"]: {"parentId": "0", "dynamicBindingPathList": [],
                                         "dynamicTriggerPathList": [], **widget}},
        "actions": [action],
    }


TABLE = {"widgetId": "t1", "widgetName": "tb_itens", "type": "TABLE_WIDGET_V2",
         "tableData": "", "primaryColumns": {}, "columnOrder": [], "dynamicPropertyPathList": []}
SELECT = {"widgetId": "s1", "widgetName": "sel_filial", "type": "SELECT_WIDGET",
          "sourceData": '[{"name":"Blue","code":"BLUE"}]', "optionLabel": "name", "optionValue": "code",
          "defaultOptionValue": "GREEN", "dynamicPropertyPathList": [{"key": "sourceData"}]}


class ConnectWidgetDataTests(unittest.TestCase):
    def use(self, s):
        self.client = FakeClient(s)
        server.client = self.client
        server.ready = True

    def persisted(self, wid):
        return find_node(self.client.persisted_dsl(), wid)

    def test_table_is_bound_like_the_data_dropdown(self):
        self.use(seed(TABLE))
        res = asyncio.run(server.connect_widget_data("t1", "q_itens"))
        self.assertTrue(res.get("persisted"), res)
        t = self.persisted("t1")
        self.assertEqual(t["tableData"], "{{q_itens.data}}")
        self.assertIn("tableData", keys(t["dynamicBindingPathList"]))
        self.assertNotIn("tableData", keys(t["dynamicPropertyPathList"]))
        self.assertEqual(t["columnOrder"], ["id", "nome_filial", "valor_total", "criado_em", "ativo"])

    def test_generated_columns_match_editor_generated_data_columns(self):
        self.use(seed(TABLE))
        asyncio.run(server.connect_widget_data("t1", "q_itens"))
        cols = self.persisted("t1")["primaryColumns"]
        nome = cols["nome_filial"]
        self.assertFalse(nome["isDerived"])
        self.assertEqual(nome["computedValue"],
                         '{{tb_itens.processedTableData.map((currentRow, currentIndex) => ( currentRow["nome_filial"]))}}')
        self.assertEqual(nome["label"], "Nome filial")
        self.assertFalse(cols["id"]["isVisible"])
        self.assertEqual(cols["valor_total"]["columnType"], "number")
        self.assertEqual(cols["valor_total"]["horizontalAlignment"], "RIGHT")
        self.assertEqual(cols["criado_em"]["columnType"], "date")
        self.assertEqual(cols["criado_em"]["inputFormat"], "YYYY-MM-DDTHH:mm:ss.SSSZ")
        self.assertEqual(cols["criado_em"]["outputFormat"], "DD/MM/YYYY HH:mm")
        self.assertEqual(cols["ativo"]["columnType"], "checkbox")
        self.assertIn("primaryColumns.nome_filial.computedValue", keys(self.persisted("t1")["dynamicBindingPathList"]))
        self.assertEqual(self.persisted("t1").get("derivedColumns", {}), {})

    def test_sql_server_dates_in_milliseconds_become_date_columns(self):
        rows = [{"criado_em": 1503430683840, "dt_venda": 1239627551093, "quantidade": 1503430683840}]
        self.use(seed(TABLE, rows=rows))
        asyncio.run(server.connect_widget_data("t1", "q_itens"))
        cols = self.persisted("t1")["primaryColumns"]
        for c in ("criado_em", "dt_venda"):
            self.assertEqual((cols[c]["columnType"], cols[c]["inputFormat"], cols[c]["outputFormat"]),
                             ("date", "Milliseconds", "DD/MM/YYYY HH:mm"))
        self.assertEqual(cols["quantidade"]["columnType"], "number")

    def test_explicit_columns_override_inference_and_can_hide_the_rest(self):
        self.use(seed(TABLE))
        asyncio.run(server.connect_widget_data("t1", "q_itens", columns=[
            {"id": "nome_filial", "label": "Filial"},
            {"id": "valor_total", "label": "Total", "columnType": "currency"},
        ], hide_unlisted=True))
        t = self.persisted("t1")
        cols = t["primaryColumns"]
        self.assertEqual(cols["nome_filial"]["label"], "Filial")
        self.assertEqual(cols["valor_total"]["currencyCode"], "BRL")
        self.assertEqual(cols["valor_total"]["decimals"], 2)
        self.assertFalse(cols["criado_em"]["isVisible"])
        self.assertEqual(t["columnOrder"][:2], ["nome_filial", "valor_total"])

    def test_table_without_sample_data_needs_columns(self):
        self.use(seed(TABLE, rows=None))
        res = asyncio.run(server.connect_widget_data("t1", "q_itens"))
        self.assertTrue(res.get("persisted"), res)
        self.assertEqual(self.persisted("t1")["tableData"], "{{q_itens.data}}")
        self.assertIn("execute_queries", res.get("warning", ""))

    def test_select_is_bound_with_label_and_value_fields(self):
        self.use(seed(SELECT))
        res = asyncio.run(server.connect_widget_data("s1", "q_itens", label_field="nome_filial", value_field="id"))
        self.assertTrue(res.get("persisted"), res)
        s = self.persisted("s1")
        self.assertEqual(s["sourceData"], "{{q_itens.data}}")
        self.assertEqual((s["optionLabel"], s["optionValue"]), ("nome_filial", "id"))
        self.assertEqual(s["defaultOptionValue"], "")
        self.assertNotIn("sourceData", keys(s["dynamicPropertyPathList"]))

    def with_execute(self, s, body_sql, rows):
        s["actions"][0]["config"]["actionConfiguration"] = {"body": body_sql}
        s["actions"][0]["config"]["pluginType"] = "DB"
        s["actions"][0]["config"]["pluginId"] = "pl_mssql"
        s["plugins"] = [{"id": "pl_mssql", "packageName": "mssql-plugin"}]
        s["responses"] = [{"match": "/api/v1/actions/execute", "method": "POST",
                           "body": {"responseMeta": {"success": True}, "data": {"isExecutionSuccess": True, "body": rows}}}]
        return s

    def executed(self):
        return [f for c in self.client.calls for f in c["fetches"] if "/api/v1/actions/execute" in f["url"]]

    def test_read_only_query_without_result_is_run_to_learn_the_columns(self):
        self.use(self.with_execute(seed(TABLE, rows=None), "  select id, nome_filial from filiais", ROWS))
        res = asyncio.run(server.connect_widget_data("t1", "q_itens"))
        self.assertTrue(self.executed())
        self.assertEqual(self.persisted("t1")["columnOrder"], ["id", "nome_filial", "valor_total", "criado_em", "ativo"])
        self.assertNotIn("warning", res)

    def test_explicit_columns_still_learn_the_other_columns(self):
        self.use(self.with_execute(seed(TABLE, rows=None), "SELECT * FROM filiais", ROWS))
        asyncio.run(server.connect_widget_data("t1", "q_itens", columns=[{"id": "nome_filial", "label": "Filial"}]))
        t = self.persisted("t1")
        self.assertEqual(t["columnOrder"], ["nome_filial", "id", "valor_total", "criado_em", "ativo"])
        self.assertEqual(t["primaryColumns"]["nome_filial"]["label"], "Filial")

    def test_writing_query_is_never_run(self):
        self.use(self.with_execute(seed(TABLE, rows=None), "UPDATE filiais SET ativo = 0; SELECT * FROM filiais", ROWS))
        res = asyncio.run(server.connect_widget_data("t1", "q_itens"))
        self.assertEqual(self.executed(), [])
        self.assertIn("warning", res)

    def instance_seed(self, data, origin_sql="SELECT * FROM filiais"):
        s = seed(TABLE, rows=None)
        s["moduleInstances"] = {"inst1": {"id": "inst1", "name": "filiais_pkg", "type": "QUERY_MODULE",
                                          "sourceModuleId": "pubm"}}
        s["moduleInstanceEntities"] = {"actions": [{"config": {"id": "pub1", "name": "_$filiais_pkg$_q_filiais",
                                                               "moduleInstanceId": "inst1", "isPublic": True},
                                                    "data": data, "isLoading": False}], "jsCollections": []}
        s["instanceRunResults"] = {"inst1": ROWS}
        s["responses"] = [
            {"match": "/api/v1/modules/pubm", "method": "GET", "body": {"responseMeta": {"success": True}, "data": {"originModuleId": "srcm"}}},
            {"match": "/api/v1/modules/srcm/entities", "method": "GET", "body": {"responseMeta": {"success": True}, "data": {
                "actions": [{"pluginType": "DB", "pluginId": "pl_mssql", "isPublic": True, "actionConfiguration": {"body": origin_sql}}]}}},
        ]
        s["plugins"] = [{"id": "pl_mssql", "packageName": "mssql-plugin"}]
        return s

    def test_query_module_instance_can_feed_a_table(self):
        self.use(self.instance_seed({"body": ROWS}))
        res = asyncio.run(server.connect_widget_data("t1", "filiais_pkg"))
        self.assertTrue(res.get("persisted"), res)
        t = self.persisted("t1")
        self.assertEqual(t["tableData"], "{{filiais_pkg.data}}")
        self.assertIn("nome_filial", t["columnOrder"])

    def test_read_only_instance_without_result_is_run_natively(self):
        self.use(self.instance_seed(None))
        res = asyncio.run(server.connect_widget_data("t1", "filiais_pkg"))
        runs = [d for c in self.client.calls for d in c["dispatched"] if d["type"] == "RUN_QUERY_MODULE_INSTANCE_INIT"]
        self.assertEqual(runs[0]["payload"], {"id": "inst1"})
        self.assertIn("nome_filial", self.persisted("t1")["columnOrder"])
        self.assertNotIn("warning", res)

    def test_writing_instance_is_never_run(self):
        self.use(self.instance_seed(None, origin_sql="EXEC sp_grava"))
        res = asyncio.run(server.connect_widget_data("t1", "filiais_pkg"))
        runs = [d for c in self.client.calls for d in c["dispatched"] if d["type"] == "RUN_QUERY_MODULE_INSTANCE_INIT"]
        self.assertEqual(runs, [])
        self.assertIn("warning", res)

    def test_run_module_instances_returns_the_result(self):
        self.use(self.instance_seed(None))
        out = asyncio.run(server.run_module_instances(["filiais_pkg"]))
        self.assertEqual((out[0]["name"], out[0]["ok"], len(out[0]["body"])), ("filiais_pkg", True, 2))

    def test_run_module_instances_blocks_a_writing_instance(self):
        self.use(self.instance_seed(None, origin_sql="DELETE FROM filiais"))
        out = asyncio.run(server.run_module_instances(["filiais_pkg"]))
        runs = [d for c in self.client.calls for d in c["dispatched"] if d["type"] == "RUN_QUERY_MODULE_INSTANCE_INIT"]
        self.assertEqual(runs, [])
        self.assertTrue(out[0]["blocked"])
        self.assertFalse(out[0]["ok"])

    def test_unknown_query_is_an_error(self):
        self.use(seed(TABLE))
        res = asyncio.run(server.connect_widget_data("t1", "q_nao_existe"))
        self.assertIn("error", res)
        self.assertIsNone(self.client.persisted_dsl())


if __name__ == "__main__":
    unittest.main()
