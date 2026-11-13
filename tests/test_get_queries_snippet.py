import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SNIPPET = REPO_ROOT / "src" / "appsmith_mcp" / "snippets" / "get_queries.js"


class GetQueriesSnippetTests(unittest.TestCase):
    def test_returns_plugin_package_name_for_execution_policy(self):
        harness = f"""
const fs = require('fs');
global.IDS = [];
global.window = {{
  __store: {{
    getState: () => ({{
      entities: {{
        actions: [{{ config: {{
          id: 'query-1', name: 'Consulta', pluginId: 'plugin-1',
          actionConfiguration: {{ body: 'SELECT 1' }}
        }} }}],
        plugins: {{ list: [{{ id: 'plugin-1', packageName: 'mssql-plugin' }}] }}
      }}
    }})
  }}
}};
const result = eval(fs.readFileSync({json.dumps(str(SNIPPET))}, 'utf8'));
process.stdout.write(JSON.stringify(result));
"""
        completed = subprocess.run(
            ["node", "-e", harness],
            check=True,
            capture_output=True,
            text=True,
        )

        result = json.loads(completed.stdout)

        self.assertEqual(result[0].get("pluginPackageName"), "mssql-plugin")

    def test_redacts_literal_sensitive_headers_but_keeps_binding_expression(self):
        harness = f"""
const fs = require('fs');
global.IDS = [];
global.window = {{
  __store: {{
    getState: () => ({{
      entities: {{
        actions: [{{ config: {{
          id: 'query-1', name: 'Consulta', pluginId: 'plugin-1',
          actionConfiguration: {{ headers: [
            {{ key: 'Authorization', value: 'Bearer segredo-literal' }},
            {{ key: 'apikey', value: '{{{{ appsmith.store.api_key }}}}' }}
          ] }}
        }} }}],
        plugins: {{ list: [{{ id: 'plugin-1', packageName: 'restapi-plugin' }}] }}
      }}
    }})
  }}
}};
const result = eval(fs.readFileSync({json.dumps(str(SNIPPET))}, 'utf8'));
process.stdout.write(JSON.stringify(result));
"""
        completed = subprocess.run(
            ["node", "-e", harness],
            check=True,
            capture_output=True,
            text=True,
        )

        headers = json.loads(completed.stdout)[0]["actionConfiguration"]["headers"]

        self.assertEqual(headers[0]["value"], "[REDACTED]")
        self.assertEqual(headers[1]["value"], "{{ appsmith.store.api_key }}")


if __name__ == "__main__":
    unittest.main()
