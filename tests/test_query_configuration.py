import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from appsmith_mcp.query_configuration import prepare_action_configuration


class QueryConfigurationTests(unittest.TestCase):
    def test_discovers_bindings_recursively_without_mutating_input(self):
        original = {
            "path": "/clientes/{{ appsmith.store.filial }}",
            "body": '{"nome": {{ JSON.stringify(inp_nome.text) }}}',
            "headers": [
                {"key": "Accept", "value": "application/json"},
                {"key": "X-Filial", "value": "{{ appsmith.store.filial }}"},
            ],
            "queryParameters": [
                {"key": "page", "value": "{{ tbl.pageNo }}"},
            ],
        }

        prepared, paths = prepare_action_configuration(original)

        self.assertEqual(
            paths,
            [
                {"key": "path"},
                {"key": "body"},
                {"key": "headers[1].value"},
                {"key": "queryParameters[0].value"},
            ],
        )
        self.assertEqual(prepared, original)
        self.assertIsNot(prepared, original)

    def test_rejects_literal_sensitive_headers_without_echoing_secret(self):
        secret = "Bearer segredo-que-nao-pode-aparecer"
        for name in ("Authorization", "apikey", "X-API-Key", "Proxy-Authorization"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "header sensível") as raised:
                    prepare_action_configuration(
                        {"headers": [{"key": name, "value": secret}]}
                    )
                self.assertNotIn(secret, str(raised.exception))

    def test_allows_sensitive_header_only_when_value_is_a_binding(self):
        config = {
            "headers": [
                {
                    "key": "Authorization",
                    "value": "Bearer {{ appsmith.store.access_token }}",
                }
            ]
        }

        prepared, paths = prepare_action_configuration(config)

        self.assertEqual(prepared, config)
        self.assertEqual(paths, [{"key": "headers[0].value"}])

    def test_rejects_sensitive_headers_nested_in_plugin_templates(self):
        config = {
            "pluginSpecifiedTemplates": [
                {
                    "value": {
                        "headers": [
                            {"key": "apikey", "value": "service-role-secret"}
                        ]
                    }
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "header sensível"):
            prepare_action_configuration(config)


if __name__ == "__main__":
    unittest.main()
