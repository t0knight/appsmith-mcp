import unittest

from appsmith_mcp.execution_policy import assess_query_action


BACKSLASH = "\\"


def action(plugin: str, **config):
    return {
        "id": "query-1",
        "name": "Lookup",
        "pluginPackageName": plugin,
        "actionConfiguration": config,
    }


class SqlReadOnlyPolicyTests(unittest.TestCase):
    def assert_allowed(self, sql, plugin="mssql-plugin"):
        decision = assess_query_action(action(plugin, body=sql))
        self.assertTrue(decision.allowed, decision.reason)

    def assert_blocked(self, sql, plugin="mssql-plugin"):
        decision = assess_query_action(action(plugin, body=sql))
        self.assertFalse(decision.allowed, f"allowed: {sql!r}")
        self.assertIn("blocked", decision.reason.lower())

    def test_allows_single_select_and_cte_select(self):
        safe_queries = (
            "SELECT 1;",
            "-- read only\nSELECT name FROM customers",
            "/* read only */ WITH active AS (SELECT id FROM customers) SELECT * FROM active;",
            "SELECT 'text; DELETE FROM customers' AS sample;",
            ";WITH active AS (SELECT id FROM customers) SELECT * FROM active;",
            "SELECT 'O''Brien' AS name",
            "SELECT [order id] FROM [orders]",
        )
        for sql in safe_queries:
            with self.subTest(sql=sql):
                self.assert_allowed(sql)

    def test_allows_tsql_temp_table_names(self):
        # '#' starts a comment only in MySQL; in T-SQL it names a temp table.
        self.assert_allowed("SELECT * FROM #recent_orders WHERE id > 10")

    def test_blocks_sql_that_can_write_or_administer(self):
        unsafe_queries = (
            "INSERT INTO customers(name) VALUES ('Alice')",
            "UPDATE customers SET name = 'Alice'",
            "DELETE FROM customers",
            "MERGE customers AS target USING source ON 1 = 0 WHEN NOT MATCHED THEN INSERT DEFAULT VALUES;",
            "EXEC dbo.sp_update_customers",
            "CREATE TABLE test (id int)",
            "ALTER TABLE customers ADD active bit",
            "DROP TABLE customers",
            "TRUNCATE TABLE customers",
            "SELECT * INTO customers_backup FROM customers",
            "WITH removed AS (DELETE FROM customers RETURNING id) SELECT * FROM removed",
            "SELECT 1; DELETE FROM customers",
            "/* SELECT 1 */ DELETE FROM customers",
            "DECLARE @x int; SELECT @x",
        )
        for sql in unsafe_queries:
            with self.subTest(sql=sql):
                self.assert_blocked(sql)

    def test_blocks_empty_or_unknown_sql_shape(self):
        for body in (None, "", "VALUES (1)"):
            with self.subTest(body=body):
                decision = assess_query_action(action("postgres-plugin", body=body))
                self.assertFalse(decision.allowed)

    def test_blocks_statements_hidden_by_dialect_specific_literals_or_comments(self):
        # Each text is a single SELECT under one engine's lexical rules but runs a DELETE
        # under another's, so the policy must reject it whatever the plugin is.
        hidden = (
            # T-SQL/Postgres: a backslash does not escape the quote, so the literal ends early.
            ("mssql-plugin", f"SELECT 'a{BACKSLASH}'; DELETE FROM t; --'"),
            # MySQL: a backslash escapes the quote, so the literal ends late.
            ("mysql-plugin", f"SELECT 'a{BACKSLASH}'' ; DELETE FROM t; --'"),
            # Postgres: $$...$$ is a string literal that can contain a quote.
            ("postgres-plugin", "SELECT $$'$$; DELETE FROM t; --'"),
            # MySQL: '#' starts a line comment that can contain a quote.
            ("mysql-plugin", "SELECT 1 #'\n; DELETE FROM t; -- '"),
            # MySQL: block comments do not nest, so the first */ closes the comment.
            ("mysql-plugin", "SELECT 1 /* /* */ ; DELETE FROM t /* */"),
        )
        for plugin, sql in hidden:
            with self.subTest(sql=sql):
                self.assert_blocked(sql, plugin)

    def test_blocks_unterminated_literals_and_comments(self):
        for sql in ("SELECT 'open", "SELECT 1 /* open", "SELECT [open", 'SELECT "open'):
            with self.subTest(sql=sql):
                self.assert_blocked(sql)


class NonSqlReadOnlyPolicyTests(unittest.TestCase):
    def test_allows_only_read_only_rest_methods(self):
        for method in ("GET", "get", "HEAD"):
            with self.subTest(method=method):
                decision = assess_query_action(action("restapi-plugin", httpMethod=method))
                self.assertTrue(decision.allowed, decision.reason)

        for method in ("POST", "PUT", "PATCH", "DELETE", None):
            with self.subTest(method=method):
                decision = assess_query_action(action("restapi-plugin", httpMethod=method))
                self.assertFalse(decision.allowed)

    def test_allows_graphql_queries_and_blocks_mutations(self):
        safe = (
            "query Customers { customers { id } }",
            "{ customers { id } }",
            '# list customers\nquery { customers(tag: "#vip") { id } }',
        )
        unsafe = (
            'mutation Create { createCustomer(name: "Alice") { id } }',
            "subscription Events { event { id } }",
            # A '#' inside a string must not hide the rest of the line as a comment.
            'query A { a(x: "#") } mutation B { deleteAll }',
        )
        for body in safe:
            with self.subTest(body=body):
                decision = assess_query_action(action("graphql-plugin", body=body))
                self.assertTrue(decision.allowed, decision.reason)
        for body in unsafe:
            with self.subTest(body=body):
                self.assertFalse(assess_query_action(action("graphql-plugin", body=body)).allowed)

    def test_allows_safe_mongo_commands_and_blocks_write_stages(self):
        for command, extra in (
            ("FIND", {}),
            ("COUNT", {}),
            ("DISTINCT", {}),
            ("AGGREGATE", {"aggregate": {"pipeline": {"data": '[{"$match": {}}]'}}}),
        ):
            with self.subTest(command=command):
                decision = assess_query_action(
                    action("mongo-plugin", formData={"command": {"data": command}, **extra})
                )
                self.assertTrue(decision.allowed, decision.reason)

        for pipeline in ('[{"$out": "copy"}]', '[{"$merge": "copy"}]'):
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

        for command in ("INSERT", "UPDATE", "DELETE", "RAW"):
            with self.subTest(command=command):
                decision = assess_query_action(
                    action("mongo-plugin", formData={"command": {"data": command}})
                )
                self.assertFalse(decision.allowed)

    def test_blocks_unknown_plugins_and_missing_metadata(self):
        for candidate in (
            action("unknown-plugin", body="SELECT 1"),
            {"id": "query-1", "actionConfiguration": {"body": "SELECT 1"}},
            {"id": "query-1", "pluginPackageName": "mssql-plugin"},
        ):
            with self.subTest(candidate=candidate):
                decision = assess_query_action(candidate)
                self.assertFalse(decision.allowed)
                self.assertIn("blocked", decision.reason.lower())


if __name__ == "__main__":
    unittest.main()
