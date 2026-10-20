import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from appsmith_mcp import server


class ServerExecutionGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ensure_ready = patch.object(server, "ensure_ready", new=AsyncMock())
        self.run_snippet = patch.object(
            server.client, "run_snippet", new=AsyncMock()
        )
        self.ensure_ready.start()
        self.run_snippet_mock = self.run_snippet.start()

    async def asyncTearDown(self):
        self.run_snippet.stop()
        self.ensure_ready.stop()

    async def test_execute_queries_runs_only_actions_approved_as_read_only(self):
        actions = [
            {
                "id": "write-query",
                "name": "Apagar_cliente",
                "pluginPackageName": "mssql-plugin",
                "actionConfiguration": {"body": "DELETE FROM clientes"},
            },
            {
                "id": "read-query",
                "name": "Consultar_clientes",
                "pluginPackageName": "mssql-plugin",
                "actionConfiguration": {"body": "SELECT * FROM clientes"},
            },
        ]
        read_result = {
            "id": "read-query",
            "name": "Consultar_clientes",
            "ok": True,
            "body": [{"id": 1}],
        }
        self.run_snippet_mock.side_effect = [actions, [read_result]]

        result = await server.execute_queries(["write-query", "read-query"])

        self.assertEqual(result[0]["id"], "write-query")
        self.assertFalse(result[0]["ok"])
        self.assertTrue(result[0]["blocked"])
        self.assertIn("somente leitura", result[0]["error"])
        self.assertEqual(result[1], read_result)
        self.assertEqual(self.run_snippet_mock.await_count, 2)
        execution_call = self.run_snippet_mock.await_args_list[1]
        self.assertEqual(
            execution_call.kwargs["json_constants"]["ACTION_IDS"],
            ["read-query"],
        )

    async def test_execute_queries_does_not_dispatch_when_every_action_is_blocked(self):
        self.run_snippet_mock.return_value = [
            {
                "id": "write-query",
                "name": "Atualizar_cliente",
                "pluginPackageName": "mssql-plugin",
                "actionConfiguration": {"body": "UPDATE clientes SET ativo = 1"},
            }
        ]

        result = await server.execute_queries(["write-query"], resolve_bindings=False)

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["blocked"])
        self.assertEqual(self.run_snippet_mock.await_count, 1)

    async def test_execute_js_functions_is_blocked_without_touching_browser(self):
        result = await server.execute_js_functions(
            [{"js_object_id": "js-1", "function_name": "executar"}]
        )

        self.assertEqual(
            result,
            [
                {
                    "jsObjectId": "js-1",
                    "functionName": "executar",
                    "ok": False,
                    "blocked": True,
                    "error": (
                        "Execução bloqueada: funções JavaScript podem produzir "
                        "efeitos colaterais."
                    ),
                }
            ],
        )
        self.run_snippet_mock.assert_not_awaited()

    async def test_run_command_is_blocked_without_touching_browser(self):
        result = await server.run_command("fetch('/api/v1/actions/execute')")

        self.assertEqual(
            result,
            {
                "ok": False,
                "blocked": True,
                "error": (
                    "Execução bloqueada: JavaScript arbitrário pode contornar "
                    "a política somente leitura."
                ),
            },
        )
        self.run_snippet_mock.assert_not_awaited()

    async def test_create_queries_adds_binding_paths_before_browser_call(self):
        self.run_snippet_mock.return_value = [{"id": "query-1"}]

        await server.create_queries(
            [
                {
                    "name": "Buscar_cliente",
                    "datasource_id": "ds-1",
                    "action_config": {
                        "path": "/clientes/{{ appsmith.store.id }}",
                        "headers": [
                            {
                                "key": "Authorization",
                                "value": "Bearer {{ appsmith.store.access_token }}",
                            }
                        ],
                    },
                }
            ]
        )

        sent = self.run_snippet_mock.await_args.kwargs["json_constants"]["QUERIES"]
        self.assertEqual(
            sent[0]["dynamic_binding_paths"],
            [{"key": "path"}, {"key": "headers[0].value"}],
        )

    async def test_create_queries_rejects_literal_secret_before_browser_call(self):
        with self.assertRaisesRegex(ValueError, "header sensível"):
            await server.create_queries(
                [
                    {
                        "name": "Insegura",
                        "datasource_id": "ds-1",
                        "action_config": {
                            "headers": [
                                {"key": "Authorization", "value": "Bearer segredo"}
                            ]
                        },
                    }
                ]
            )

        self.run_snippet_mock.assert_not_awaited()

    async def test_update_queries_rebuilds_binding_paths_from_merged_config(self):
        existing = [
            {
                "id": "query-1",
                "name": "Buscar_cliente",
                "actionConfiguration": {
                    "path": "/clientes/{{ appsmith.store.id }}",
                    "headers": [{"key": "Accept", "value": "application/json"}],
                },
            }
        ]
        self.run_snippet_mock.side_effect = [existing, [{"id": "query-1"}]]

        await server.update_queries(
            [
                {
                    "query_id": "query-1",
                    "action_config": {"body": "{{ JSON.stringify(inp.text) }}"},
                }
            ]
        )

        sent = self.run_snippet_mock.await_args_list[1].kwargs["json_constants"][
            "UPDATES"
        ]
        self.assertEqual(
            sent[0]["action_config"],
            {
                "path": "/clientes/{{ appsmith.store.id }}",
                "headers": [{"key": "Accept", "value": "application/json"}],
                "body": "{{ JSON.stringify(inp.text) }}",
            },
        )
        self.assertEqual(
            sent[0]["dynamic_binding_paths"],
            [{"key": "path"}, {"key": "body"}],
        )

    async def test_get_store_uses_read_only_inspection_snippet(self):
        self.run_snippet_mock.return_value = {"store": {"filial": "001"}}

        result = await server.get_store(["filial"])

        self.assertEqual(result, {"store": {"filial": "001"}})
        self.assertEqual(
            self.run_snippet_mock.await_args.kwargs["json_constants"],
            {"MODE": "get_store", "ARG": {"keys": ["filial"]}},
        )

    async def test_eval_value_uses_read_only_inspection_snippet(self):
        self.run_snippet_mock.return_value = {"found": True, "value": 7}

        result = await server.eval_value("Tabela1.selectedRow.id")

        self.assertTrue(result["found"])
        self.assertEqual(
            self.run_snippet_mock.await_args.kwargs["json_constants"],
            {
                "MODE": "eval_value",
                "ARG": {"path": "Tabela1.selectedRow.id"},
            },
        )

    async def test_list_children_uses_read_only_inspection_snippet(self):
        self.run_snippet_mock.return_value = [{"id": "child-1"}]

        result = await server.list_children("modal-1")

        self.assertEqual(result, [{"id": "child-1"}])
        self.assertEqual(
            self.run_snippet_mock.await_args.kwargs["json_constants"],
            {"MODE": "list_children", "ARG": {"parent_id": "modal-1"}},
        )

    async def test_get_datasource_uses_masked_read_only_inspection_snippet(self):
        self.run_snippet_mock.return_value = {
            "id": "ds-1",
            "environments": [
                {"datasourceConfiguration": {"password": "[REDACTED]"}}
            ],
        }

        result = await server.get_datasource("ds-1")

        self.assertEqual(
            result["environments"][0]["datasourceConfiguration"]["password"],
            "[REDACTED]",
        )
        self.assertEqual(
            self.run_snippet_mock.await_args.kwargs["json_constants"],
            {
                "MODE": "get_datasource",
                "ARG": {"datasource_id": "ds-1"},
            },
        )


if __name__ == "__main__":
    unittest.main()
