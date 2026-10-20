import asyncio
import unittest

from appsmith_mcp import server
from tests.snippet_harness import FakeClient, find_node, keys, root_widget


def table_seed(**extra):
    table = {
        "widgetId": "t1", "widgetName": "tb_itens", "type": "TABLE_WIDGET_V2", "parentId": "0",
        "tableData": "{{q_itens.data}}", "primaryColumns": {}, "columnOrder": [],
        "dynamicBindingPathList": [{"key": "tableData"}], "dynamicTriggerPathList": [],
        "dynamicPropertyPathList": [{"key": "tableData"}],
        **extra,
    }
    return {"widgets": {"0": root_widget(["t1"]), "t1": table}}


class TableColumnTests(unittest.TestCase):
    def use(self, seed):
        self.client = FakeClient(seed)
        server.client = self.client
        server.ready = True

    def table(self):
        return find_node(self.client.persisted_dsl(), "t1")

    def test_per_row_colour_is_shown_as_code_but_label_is_not(self):
        self.use(table_seed())
        asyncio.run(server.manage_table_columns("t1", add=[{
            "id": "acoes", "onClick": "{{ q_x.run() }}",
            "buttonLabel": "{{ currentRow.ativo ? 'Inativar' : 'Ativar' }}",
            "buttonColor": "{{ currentRow.ativo ? '#D97706' : '#16A34A' }}",
            "buttonVariant": "SECONDARY",
        }]))
        dyn = keys(self.table()["dynamicPropertyPathList"])
        self.assertIn("primaryColumns.acoes.buttonColor", dyn)
        self.assertNotIn("primaryColumns.acoes.buttonLabel", dyn)
        self.assertNotIn("primaryColumns.acoes.buttonVariant", dyn)
        self.assertIn("tableData", dyn)

    def test_currency_columns_default_to_brazilian_real(self):
        self.use(table_seed())
        asyncio.run(server.manage_table_columns("t1", from_schema=[{"id": "valor", "columnType": "currency"}]))
        col = self.table()["primaryColumns"]["valor"]
        self.assertEqual(col["currencyCode"], "BRL")
        self.assertEqual(col["decimals"], 2)

    def test_configure_sets_number_and_date_formats(self):
        self.use(table_seed(primaryColumns={
            "dt": {"id": "dt", "originalId": "dt", "label": "dt", "columnType": "text", "index": 0},
            "vl": {"id": "vl", "originalId": "vl", "label": "vl", "columnType": "text", "index": 1},
        }, columnOrder=["dt", "vl"]))
        asyncio.run(server.manage_table_columns("t1", configure=[
            {"id": "dt", "label": "Data", "columnType": "date",
             "dateInputFormat": "YYYY-MM-DDTHH:mm:ss", "dateOutputFormat": "DD/MM/YYYY"},
            {"id": "vl", "label": "Valor", "columnType": "currency", "decimals": 2},
        ]))
        cols = self.table()["primaryColumns"]
        self.assertEqual(cols["dt"]["inputFormat"], "YYYY-MM-DDTHH:mm:ss")
        self.assertEqual(cols["dt"]["outputFormat"], "DD/MM/YYYY")
        self.assertEqual(cols["vl"]["currencyCode"], "BRL")
        self.assertEqual(cols["vl"]["decimals"], 2)
        self.assertEqual(cols["vl"]["horizontalAlignment"], "RIGHT")


if __name__ == "__main__":
    unittest.main()


class ColumnPanelGuardTests(unittest.TestCase):
    """Column properties must stay readable in the column editor too."""

    def use(self, seed):
        self.client = FakeClient(seed)
        server.client = self.client
        server.ready = True

    def test_currentrow_props_are_still_allowed(self):
        # The column editor evaluates these per row; refusing them would break what works.
        self.use(table_seed())
        asyncio.run(server.manage_table_columns("t1", add=[{
            "id": "acao", "columnType": "button", "onClick": "{{ q.run() }}",
            "buttonColor": "{{ currentRow.banido ? '#16A34A' : '#D97706' }}",
        }]))

    def test_hidden_binding_on_column_is_refused(self):
        self.use(table_seed(primaryColumns={
            "nome": {"id": "nome", "originalId": "nome", "label": "nome",
                     "columnType": "text", "index": 0},
        }, columnOrder=["nome"]))
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(server.manage_table_columns(
                "t1", configure=[{"id": "nome", "hidden": "{{ chk.isChecked }}"}]))
        self.assertIn("allow_bindings", str(ctx.exception))
        self.assertIn("t1.primaryColumns.nome.hidden", str(ctx.exception))

    def test_authorised_column_binding_passes(self):
        self.use(table_seed(primaryColumns={
            "nome": {"id": "nome", "originalId": "nome", "label": "nome",
                     "columnType": "text", "index": 0},
        }, columnOrder=["nome"]))
        asyncio.run(server.manage_table_columns(
            "t1", configure=[{"id": "nome", "hidden": "{{ chk.isChecked }}"}],
            allow_bindings=["t1.primaryColumns.nome.hidden"]))
