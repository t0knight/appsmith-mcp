import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SNIPPETS = REPO_ROOT / "src" / "appsmith_mcp" / "snippets"


def run_node(script: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


class QuerySnippetTests(unittest.TestCase):
    def test_create_query_sends_dynamic_binding_path_list(self):
        snippet = SNIPPETS / "create_queries.js"
        script = f"""
const fs = require('fs');
let sent = null;
global.QUERIES = [{{
  name: 'Consulta', datasource_id: 'ds-1',
  action_config: {{ path: '/clientes/{{{{ appsmith.store.id }}}}' }},
  dynamic_binding_paths: [{{ key: 'path' }}]
}}];
global.DEFAULTS = {{}};
global.document = {{ cookie: '' }};
global.window = {{ __store: {{
  getState: () => ({{
    entities: {{
      datasources: {{ list: [{{ id: 'ds-1', pluginId: 'plugin-1', workspaceId: 'ws-1' }}] }},
      plugins: {{ list: [{{ id: 'plugin-1', packageName: 'restapi-plugin' }}] }},
      pageList: {{ currentPageId: 'page-1' }}
    }},
    ui: {{ applications: {{ currentApplication: {{ id: 'app-1' }} }} }}
  }}),
  dispatch: () => undefined
}} }};
global.fetch = async (_url, options) => {{
  sent = JSON.parse(options.body);
  return {{ status: 200, json: async () => ({{ responseMeta: {{ success: true }}, data: {{ id: 'query-1' }} }}) }};
}};
(async () => {{
  await eval(fs.readFileSync({json.dumps(str(snippet))}, 'utf8'));
  process.stdout.write(JSON.stringify(sent));
}})().catch(error => {{ console.error(error); process.exit(1); }});
"""

        sent = run_node(script)

        self.assertEqual(sent.get("dynamicBindingPathList"), [{"key": "path"}])

    def test_update_query_sends_rebuilt_dynamic_binding_path_list(self):
        snippet = SNIPPETS / "update_queries.js"
        script = f"""
const fs = require('fs');
let sent = null;
global.UPDATES = [{{
  query_id: 'query-1',
  action_config: {{ body: '{{{{ inp.text }}}}' }},
  dynamic_binding_paths: [{{ key: 'body' }}]
}}];
global.document = {{ cookie: '' }};
global.window = {{ __store: {{
  getState: () => ({{
    entities: {{ actions: [{{ config: {{
      id: 'query-1', name: 'Consulta', actionConfiguration: {{ body: 'SELECT 1' }}
    }} }}] }},
    ui: {{ applications: {{ currentApplication: {{ id: 'app-1' }} }} }}
  }}),
  dispatch: () => undefined
}} }};
global.fetch = async (_url, options) => {{
  sent = JSON.parse(options.body);
  return {{ status: 200, json: async () => ({{ responseMeta: {{ success: true }}, data: {{ id: 'query-1' }} }}) }};
}};
(async () => {{
  await eval(fs.readFileSync({json.dumps(str(snippet))}, 'utf8'));
  process.stdout.write(JSON.stringify(sent));
}})().catch(error => {{ console.error(error); process.exit(1); }});
"""

        sent = run_node(script)

        self.assertEqual(sent.get("dynamicBindingPathList"), [{"key": "body"}])

    def test_update_query_repoints_to_saved_datasource(self):
        snippet = SNIPPETS / "update_queries.js"
        script = f"""
const fs = require('fs');
let sent = null;
global.UPDATES = [{{ query_id: 'query-1', datasource_id: 'ds-n8n' }}];
global.document = {{ cookie: '' }};
global.window = {{ __store: {{
  getState: () => ({{
    entities: {{
      actions: [{{ config: {{
        id: 'query-1', name: 'envia', pluginId: 'rest',
        datasource: {{ name: 'DEFAULT_REST_DATASOURCE', datasourceConfiguration: {{ url: 'https://n8n' }} }},
        actionConfiguration: {{ path: '/webhook/x' }}
      }} }}],
      datasources: {{ list: [{{ id: 'ds-n8n', name: 'N8N', pluginId: 'rest', workspaceId: 'ws-1' }}] }}
    }},
    ui: {{ applications: {{ currentApplication: {{ id: 'app-1' }} }} }}
  }}),
  dispatch: () => undefined
}} }};
global.fetch = async (_url, options) => {{
  sent = JSON.parse(options.body);
  return {{ status: 200, json: async () => ({{ responseMeta: {{ success: true }}, data: {{ id: 'query-1' }} }}) }};
}};
(async () => {{
  await eval(fs.readFileSync({json.dumps(str(snippet))}, 'utf8'));
  process.stdout.write(JSON.stringify(sent));
}})().catch(error => {{ console.error(error); process.exit(1); }});
"""

        sent = run_node(script)

        self.assertEqual(sent["datasource"], {"id": "ds-n8n", "name": "N8N", "pluginId": "rest", "workspaceId": "ws-1"})
        self.assertEqual(sent["actionConfiguration"], {"path": "/webhook/x"})

    def test_update_datasource_config_goes_through_datasource_storages(self):
        snippet = SNIPPETS / "update_datasources.js"
        script = f"""
const fs = require('fs');
const calls = [];
global.UPDATES = [{{ datasource_id: 'ds-1', datasource_config: {{ url: 'http://n8n:5678', headers: [{{ key: 'X-T', value: 'k' }}] }} }}];
global.document = {{ cookie: '' }};
global.window = {{ __store: {{
  getState: () => ({{ entities: {{ datasources: {{ list: [{{
    id: 'ds-1', name: 'N8N', workspaceId: 'ws-1',
    datasourceStorages: {{ 'env-1': {{ environmentId: 'env-1', datasourceConfiguration: {{ url: 'https://old', queryParameters: [] }} }} }}
  }}] }} }} }}),
  dispatch: () => undefined
}} }};
global.fetch = async (url, options) => {{
  calls.push({{ url, body: JSON.parse(options.body) }});
  return {{ status: 200, json: async () => ({{ responseMeta: {{ success: true }}, data: {{}} }}) }};
}};
(async () => {{
  await eval(fs.readFileSync({json.dumps(str(snippet))}, 'utf8'));
  process.stdout.write(JSON.stringify(calls));
}})().catch(error => {{ console.error(error); process.exit(1); }});
"""

        calls = run_node(script)

        self.assertEqual([c["url"] for c in calls], ["/api/v1/datasources/datasource-storages"])
        body = calls[0]["body"]
        self.assertEqual(body["datasourceId"], "ds-1")
        self.assertEqual(body["environmentId"], "env-1")
        self.assertEqual(body["datasourceConfiguration"], {
            "url": "http://n8n:5678", "queryParameters": [], "headers": [{"key": "X-T", "value": "k"}],
        })


if __name__ == "__main__":
    unittest.main()
