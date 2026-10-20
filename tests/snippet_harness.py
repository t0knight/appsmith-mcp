"""Run the real MCP snippets in Node against a fake Appsmith Redux store.

`FakeClient` stands in for `BiDiClient`: it composes the script with the same
`build_snippet_script` the real client uses, then evaluates it in Node with a minimal
`window.__store` (canvasWidgets / actions / page context), a recording `fetch`, and the
dispatch handlers the snippets rely on. Each call's evidence (dispatched actions, HTTP
requests, final widgets) is kept on the client for assertions.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from appsmith_mcp.bidi import build_snippet_script

FAKE_ENV_JS = r"""
const __log = { dispatched: [], fetches: [] };
const __state = {
  entities: {
    canvasWidgets: __SEED.widgets,
    actions: __SEED.actions || [],
    jsActions: __SEED.jsActions || [],
    pageList: { currentPageId: "p1", applicationId: "a1", pages: [{ pageId: "p1", pageName: "Page1" }] },
    app: { store: {} },
    moduleInstances: __SEED.moduleInstances || {},
    modules: __SEED.moduleEntities || {},
    moduleInstanceEntities: __SEED.moduleInstanceEntities || { actions: [], jsCollections: [] },
    datasources: { list: __SEED.datasources || [] },
    plugins: { list: __SEED.plugins || [] },
  },
  ui: {
    pageWidgets: { p1: { layoutId: "l1" } },
    applications: { currentApplication: { id: "a1", name: "App" } },
    editor: { currentPageId: "p1", loadingStates: {} },
    appTheming: { selectedTheme: { properties: { colors: { primaryColor: "#553DE9" } } } },
    ...(__SEED.ui || {}),
  },
  evaluations: { tree: {} },
};
let __n = 1;
const __subs = new Set();
globalThis.window = globalThis;
globalThis.document = { cookie: "XSRF-TOKEN=x", location: { href: __SEED.url || "http://appsmith/app/a/page1-p1/edit" } };
window.location = document.location;
window.__store = {
  getState: () => __state,
  subscribe: (fn) => { __subs.add(fn); return () => __subs.delete(fn); },
  dispatch: (a) => {
    __log.dispatched.push(JSON.parse(JSON.stringify(a)));
    const cw = __state.entities.canvasWidgets;
    if (a.type === "BATCH_UPDATE_WIDGET_PROPERTY") {
      const w = cw[a.payload.widgetId];
      if (w) Object.assign(w, JSON.parse(JSON.stringify(a.payload.updates.modify || {})));
    } else if (a.type === "WIDGET_ADD_CHILD") {
      const p = a.payload;
      const defaults = JSON.parse(JSON.stringify((__SEED.defaults || {})[p.type] || {}));
      cw[p.newWidgetId] = {
        dynamicBindingPathList: [], dynamicTriggerPathList: [],
        ...defaults,
        widgetId: p.newWidgetId, type: p.type, parentId: p.widgetId,
        widgetName: p.type.split("_")[0].toLowerCase() + (__n++),
        leftColumn: p.leftColumn, topRow: p.topRow,
        rightColumn: p.leftColumn + p.columns, bottomRow: p.topRow + p.rows,
      };
      const parent = cw[p.widgetId];
      if (parent) parent.children = [...(parent.children || []), p.newWidgetId];
    } else if (a.type === "RUN_QUERY_MODULE_INSTANCE_INIT") {
      // Emulates the editor running a query-module instance: its public action gets the result.
      const pub = (__state.entities.moduleInstanceEntities.actions || [])
        .find(x => x.config.moduleInstanceId === a.payload.id && x.config.isPublic);
      const rows = (__SEED.instanceRunResults || {})[a.payload.id];
      if (pub && rows) setTimeout(() => { pub.data = { body: rows, isExecutionSuccess: true }; pub.isLoading = false; }, 30);
    } else if (a.type === "UPDATE_LAYOUT" && __state.ui.editor.currentModuleId && __SEED.editorSaves !== false) {
      // Emulates the package module editor: take the widgets, save the module layout (debounced),
      // then refresh the module entity with the saved DSL.
      const widgets = JSON.parse(JSON.stringify(a.payload.widgets));
      __state.entities.canvasWidgets = widgets;
      const mid = __state.ui.editor.currentModuleId;
      const mod = __state.entities.modules[mid];
      const build = id => { const n = { ...widgets[id] }; if (Array.isArray(n.children)) n.children = n.children.map(build); return n; };
      setTimeout(() => {
        const dsl = build("0");
        const mc = (dsl.children || []).find(c => c.type === "MODULE_CONTAINER_WIDGET");
        if (mc) for (const k of ["inputsForm", "outputsForm", "onInputChangeConfig", "dynamicTriggerPathList"]) delete mc[k];
        __log.fetches.push({ url: `/api/v1/layouts/${mod.layouts[0].id}/modules/${mid}?packageId=${mod.packageId}`, method: "PUT", body: { dsl } });
        __state.entities.modules = { ...__state.entities.modules, [mid]: { ...mod, layouts: [{ ...mod.layouts[0], dsl }] } };
        for (const fn of __subs) fn();
      }, 50);
    }
    for (const fn of __subs) fn();
    return a;
  },
};
globalThis.fetch = async (url, opts = {}) => {
  let body = opts.body;
  try { body = body ? JSON.parse(body) : body; } catch (e) {}
  __log.fetches.push({ url, method: opts.method || "GET", body });
  const hit = (__SEED.responses || []).find(r => url.includes(r.match) && (!r.method || r.method === (opts.method || "GET")));
  const status = hit ? (hit.status || 200) : 200;
  // `bodies` answers successive calls in order (the last one repeats).
  const payload = !hit ? { responseMeta: { status: 200, success: true }, data: {} }
    : hit.bodies ? (hit.bodies.length > 1 ? hit.bodies.shift() : hit.bodies[0]) : hit.body;
  return { status, ok: status < 300, json: async () => payload, text: async () => JSON.stringify(payload) };
};
"""

RUNNER_JS = r"""
const fs = require("fs");
const __SEED = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const __script = fs.readFileSync(process.argv[3], "utf8");
%ENV%
(async () => {
  let result, error = null;
  try { result = await eval(__script); } catch (e) { error = String(e && e.stack || e); }
  process.stdout.write(JSON.stringify({
    result, error,
    widgets: __state.entities.canvasWidgets,
    dispatched: __log.dispatched, fetches: __log.fetches,
  }));
  process.exit(0);
})();
""".replace("%ENV%", FAKE_ENV_JS)


def root_widget(children=()):
    return {"widgetId": "0", "widgetName": "MainContainer", "type": "CANVAS_WIDGET",
            "parentId": None, "children": list(children),
            "dynamicBindingPathList": [], "dynamicTriggerPathList": []}


class FakeClient:
    """Drop-in for BiDiClient.run_snippet that evaluates in Node against `seed`."""

    def __init__(self, seed):
        self.seed = seed
        self.calls = []
        self.last = None
        self.ws = None

    async def connect(self):
        return None

    async def reset(self):
        return None

    async def run_snippet(self, snippet, json_constants=None, js_helpers=None, wait_for_save=False):
        script = build_snippet_script(snippet, json_constants, js_helpers, wait_for_save)
        with tempfile.TemporaryDirectory() as tmp:
            seed_path = Path(tmp) / "seed.json"
            script_path = Path(tmp) / "script.js"
            runner_path = Path(tmp) / "runner.js"
            seed_path.write_text(json.dumps(self.seed), encoding="utf-8")
            script_path.write_text(script, encoding="utf-8")
            runner_path.write_text(RUNNER_JS, encoding="utf-8")
            proc = subprocess.run(
                ["node", str(runner_path), str(seed_path), str(script_path)],
                capture_output=True, text=True, encoding="utf-8", timeout=60,
            )
        if proc.returncode != 0 or not proc.stdout:
            raise RuntimeError(f"node failed: {proc.stderr[-2000:]}")
        out = json.loads(proc.stdout)
        if out.get("error"):
            raise RuntimeError(out["error"])
        # Carry the mutated store into the next call, like a live editor would.
        self.seed = {**self.seed, "widgets": out["widgets"]}
        self.calls.append(out)
        self.last = out
        return out["result"]

    def persisted_dsl(self):
        """The DSL tree of the last layout PUT across all calls (or None)."""
        for call in reversed(self.calls):
            for f in reversed(call["fetches"]):
                if f["method"] == "PUT" and "/api/v1/layouts/" in f["url"]:
                    return f["body"]["dsl"]
        return None


def find_node(tree, widget_id):
    if tree is None:
        return None
    if tree.get("widgetId") == widget_id:
        return tree
    for c in tree.get("children") or []:
        hit = find_node(c, widget_id)
        if hit:
            return hit
    return None


def keys(path_list):
    return sorted(p["key"] for p in (path_list or []))
