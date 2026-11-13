import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from appsmith_mcp.execution_policy import assess_query_action


def action(plugin: str, **config):
    return {
        "id": "query-1",
        "name": "Consulta",
        "pluginPackageName": plugin,
        "actionConfiguration": config,
    }


class SqlReadOnlyPolicyTests(unittest.TestCase):
    def test_allows_single_select_and_cte_select(self):
        safe_queries = (
            "SELECT 1;",
            "-- leitura\nSELECT nome FROM clientes",
            "/* leitura */ WITH ativos AS (SELECT id FROM clientes) SELECT * FROM ativos;",
            "SELECT 'texto; DELETE FROM clientes' AS exemplo;",
            ";WITH ativos AS (SELECT id FROM clientes) SELECT * FROM ativos;",
        )

        for sql in safe_queries:
            with self.subTest(sql=sql):
                decision = assess_query_action(action("mssql-plugin", body=sql))
                self.assertTrue(decision.allowed, decision.reason)

    def test_blocks_sql_that_can_write_or_administer(self):
        unsafe_queries = (
            "INSERT INTO clientes(nome) VALUES ('Ana')",
            "UPDATE clientes SET nome = 'Ana'",
            "DELETE FROM clientes",
            "MERGE clientes AS destino USING origem ON 1 = 0 WHEN NOT MATCHED THEN INSERT DEFAULT VALUES;",
            "EXEC dbo.sp_atualizar_clientes",
            "CREATE TABLE teste (id int)",
            "ALTER TABLE clientes ADD ativo bit",
            "DROP TABLE clientes",
            "TRUNCATE TABLE clientes",
            "SELECT * INTO clientes_backup FROM clientes",
            "WITH removidos AS (DELETE FROM clientes RETURNING id) SELECT * FROM removidos",
            "SELECT 1; DELETE FROM clientes",
            "/* SELECT 1 */ DELETE FROM clientes",
            "DECLARE @x int; SELECT @x",
        )

        for sql in unsafe_queries:
            with self.subTest(sql=sql):
                decision = assess_query_action(action("mssql-plugin", body=sql))
                self.assertFalse(decision.allowed)
                self.assertIn("bloqueada", decision.reason.lower())

    def test_blocks_empty_or_unknown_sql_shape(self):
        for body in (None, "", "VALUES (1)"):
            with self.subTest(body=body):
                decision = assess_query_action(action("postgres-plugin", body=body))
                self.assertFalse(decision.allowed)


class NonSqlReadOnlyPolicyTests(unittest.TestCase):
    def test_allows_only_read_only_rest_methods(self):
        for method in ("GET", "get", "HEAD"):
            with self.subTest(method=method):
                decision = assess_query_action(action("restapi-plugin", httpMethod=method))
                self.assertTrue(decision.allowed, decision.reason)

        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                decision = assess_query_action(action("restapi-plugin", httpMethod=method))
                self.assertFalse(decision.allowed)

    def test_allows_graphql_queries_and_blocks_mutations(self):
        safe = ("query Clientes { clientes { id } }", "{ clientes { id } }")
        unsafe = (
            "mutation Criar { criarCliente(nome: \"Ana\") { id } }",
            "subscription Eventos { evento { id } }",
        )

        for body in safe:
            with self.subTest(body=body):
                self.assertTrue(
                    assess_query_action(action("graphql-plugin", body=body)).allowed
                )
        for body in unsafe:
            with self.subTest(body=body):
                self.assertFalse(
                    assess_query_action(action("graphql-plugin", body=body)).allowed
                )

    def test_allows_safe_mongo_commands_and_blocks_write_stages(self):
        for command, extra in (
            ("FIND", {}),
            ("COUNT", {}),
            ("DISTINCT", {}),
            ("AGGREGATE", {"aggregate": {"pipeline": {"data": '[{"$match": {}}]'}}}),
        ):
            with self.subTest(command=command):
                decision = assess_query_action(
                    action(
                        "mongo-plugin",
                        formData={"command": {"data": command}, **extra},
                    )
                )
                self.assertTrue(decision.allowed, decision.reason)

        for pipeline in ('[{"$out": "copia"}]', '[{"$merge": "copia"}]'):
            with self.subTest(pipeline=pipeline):
                decision = assess_query_action(
                    action(
                        "mongo-plugin",
                        formData={
                            "command": {"data": "AGGREGATE"},
                            "aggregate": {"pipeline": {"data": pipeline}},
                        },
                    )
                )
                self.assertFalse(decision.allowed)

        for command in ("INSERT", "UPDATE", "DELETE"):
            with self.subTest(command=command):
                decision = assess_query_action(
                    action(
                        "mongo-plugin",
                        formData={"command": {"data": command}},
                    )
                )
                self.assertFalse(decision.allowed)

    def test_blocks_unknown_plugins_and_missing_metadata(self):
        for candidate in (
            action("unknown-plugin", body="SELECT 1"),
            {"id": "query-1", "actionConfiguration": {"body": "SELECT 1"}},
        ):
            with self.subTest(candidate=candidate):
                decision = assess_query_action(candidate)
                self.assertFalse(decision.allowed)
                self.assertIn("bloqueada", decision.reason.lower())


if __name__ == "__main__":
    unittest.main()
