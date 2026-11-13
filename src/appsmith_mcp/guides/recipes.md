# Appsmith MCP — Recipes & implicit contracts

Patterns that aren't bugs but cost discovery cycles. Written for an agent driving the MCP so a
"simple prompt → complete build" doesn't stall on an undocumented contract. Each recipe names the
tools involved and the gotcha.

---

## 1. Download a binary file produced by a webhook (n8n / any HTTP endpoint)

When a query's response IS a file (zip/xlsx/pdf) rather than JSON, **`query.data` is already a blob
URL** — do not base64-encode it yourself.

- The REST query receives the raw binary (the webhook replies with a *Binary* response, not JSON).
- Appsmith exposes the response as a blob URL at `<query>.data`.
- Download it with the framework's `download(...)`, then release the URL:

```js
await envia_n8n.run({ finalidade, dados_bancarios, pagamento });
await download(envia_n8n.data, `PAGAMENTOS - ${hoje}.zip`, "application/zip");
URL.revokeObjectURL(envia_n8n.data);
```

Put this in a JS object function and wire it to the button's `onClick`. The base64-JSON path also
works but is the fragile one — prefer the blob URL.

## 2. Consume a CORS-restricted external API → use a server-side REST query, not `fetch` in a custom widget

A Custom Widget runs in a **cross-origin sandboxed iframe**, so `fetch()` from inside it is blocked
by CORS for restricted sources (e.g. an RSS/news proxy). A CORS-open API (some currency/weather
endpoints) works from the iframe, which is why it's inconsistent.

The reliable pattern for any external data:
- Create a **REST datasource + query** (`create_datasources` / `create_queries`). The Appsmith
  **server** makes the request, so there is no CORS.
- Parse/shape the result in a JS object if needed (e.g. RSS XML → array).
- Feed the result into the widget via `default_model` (see the JSON-string boundary note below).

## 3. Custom-widget model values arrive as JSON strings

Any NON-string value bound into a Custom Widget's `default_model` reads back inside the widget as a
**JSON string**, not its native type:

- `model.rows` bound to `{{ q.data }}` (an array) → `appsmith.model.rows` is `"[{...}]"` (string).
- `model.loading` bound to `{{ q.isLoading }}` (a boolean) → `"false"` (a truthy string!).

Parse defensively inside the widget:

```js
let rows = appsmith.model.rows;
if (typeof rows === "string") { try { rows = JSON.parse(rows); } catch (e) { rows = []; } }
const loading = String(appsmith.model.loading) === "true";
```

Plain string bindings (a name, a label) pass through untouched.

## 4. Run a query when the page opens

Setting a query's `runBehaviour: "ON_PAGE_LOAD"` (via `update_queries`) is **not enough on its own**
— the page's `layoutOnLoadActions` must be regenerated too, or the query never fires. Use
`set_page_load_actions([queryId])`: it sets `runBehaviour` AND re-saves the layout so the server
recomputes the on-load schedule, then reads it back so you can confirm. Be on the page that owns the
query (`switch_page` first). `refresh_page` to see it run immediately.

## 5. Per-row button label/color in a table

An action column whose label or color depends on the row uses `currentRow` — but the value must be
an array mapped over `processedTableData`. `manage_table_columns` auto-wraps this, so just write the
natural expression:

```jsonc
manage_table_columns(tableId, { add: [{
  id: "acao_status", label: "Status", columnType: "button",
  buttonLabel: "{{ currentRow.banido ? 'Reativar' : 'Inativar' }}",
  buttonColor: "{{ currentRow.banido ? '#16A34A' : '#D97706' }}",
  onClick:     "{{ gestaoJS.confirmarStatus(currentRow) }}"
}]})
```

Read the clicked row in `onClick` via `{{ <table>.triggeredRow }}` (NOT `selectedRow`).

## 6. Add a child to a modal/container/tabs

Pass the wrapper's id as `parent_id` to `add_widgets` — it auto-redirects to the wrapper's inner
canvas so the child actually renders (the result reports `redirectedToInnerCanvas`). You no longer
need to add-then-`reparent_widgets`.

## 7. Two icon universes

Native `ICON_WIDGET` / `ICON_BUTTON_WIDGET` / `BUTTON_WIDGET` / table `iconButton` columns use
**Blueprint** icon names — look them up with `list_icon_names("cart")`. Custom widgets use whatever
icon font YOU load (Tabler, Font Awesome, …). The same string can differ: `robot` is a Tabler icon
(works in a custom widget) but is NOT a Blueprint icon (renders blank on a native ICON_WIDGET, with
no error).

## 8. Testing a session-token-authenticated query

After updating UI session state with `set_store`,
the eval worker needs a moment to resync before a query's `{{appsmith.store.*}}` header resolves to
the new value. `execute_queries` waits for that sync by default (`await_eval`); if a query still
reports the old auth state on the first call, `refresh_page` and run it again.

Only execute a query when the read-only execution policy permits it. The MCP blocks
`execute_js_functions` and `run_command`; authoring a JS function does not authorise
the agent to execute it. Never put literal tokens in source or query headers.


## Build like a person would (maintainability)

- Feed tables/selects with `connect_widget_data(widget, query)`: the Data dropdown shows the query,
  columns get readable labels, ids are hidden, numbers are right-aligned, dates/currency formatted.
  Shape data in the query's SQL, not in `{{ q.data.map(...) }}`.
- `{{ query.data }}` with spaces is not recognised by the Data dropdown — the MCP normalises it.
- Any binding on a property with a visual control (switch, dropdown, colour) is stored with the
  "JS" toggle on, otherwise the pane shows the control and hides the code. `lint_design` reports
  `binding_hidden_in_ui` for pages built another way.
- Run behaviour: MANUAL by default (call from the event), ON_PAGE_LOAD only for what the screen
  shows on open, AUTOMATIC only with a reason (`set_run_behaviour`); `lint_design` flags AUTOMATIC.

## Packages

1. `list_packages` → `get_package(id)` → `open_module(package, module)`.
2. Query module: `get_queries` / `update_queries` (inputs are `{{inputs.x}}`). JS module:
   `update_js_objects`. UI module: widget tools + `create_queries` / `create_js_objects`
   (module-level) — saves go through the module editor itself.
3. Contract: `update_module(inputs=[...], outputs=[...])`.
4. `publish_package(id, confirm=True)` — only after the user agrees (every consuming app is affected).
5. In an app page: `update_app_packages` (the editor also upgrades on open), then
   `add_module_instances` / `update_module_instances` / `run_module_instances`, and
   `connect_widget_data(table, "<query instance>")`.

## Reading state without large payloads

Start with `get_capabilities` for registered tools and policy, then `get_build_context`
to check the current app/page/module. Capability discovery does not inspect the browser.

- `list_widgets`: ids, names, types and bounds, without full properties or sources.
- `list_children(parent_id)`: direct children of a container/modal/canvas.
- `dump_state(sections=["connections"])`: compact widget tree plus binding/event references,
  without full widget source, query SQL or JS bodies.
- `get_widget(widget_id, fields=["text", "isVisible"])`: only the properties you need.
- `get_queries` / `get_js_objects` / `get_custom_widget`: source only when it is needed.
- `export_page(summary=True)`: structural summary of the persisted page DSL. It covers the
  page's widget layout, not queries or JS objects. `save_to_path` writes a local file.

Avoid an unrestricted `dump_state(verbose=True)` for routine discovery. Text-based
connection references are hints, not a complete dependency graph of arbitrary JavaScript.

## Diagnosing and verifying a saved change

1. Call `get_build_context`: confirm the intended app/page/module and `consistent` state.
   Use `switch_page` / `open_module` before authoring another page/module.
2. Apply the smallest targeted change. `configure_table` and `set_validation` accept named
   options/rules; omitted/None values are unchanged, while false/zero/empty text are written.
3. Check persistence in the result. These two helpers raise on an unconfirmed save.
   `set_widget_events` returns `ok`/`persisted` per event, preserves mixed-success batches,
   and raises if every target failed. Repeated widget/event pairs are saved/reported once,
   using the last code supplied. Inspect errors before continuing.
4. Re-read the affected values. For page persistence verification, reload when appropriate
   and inspect again. A screenshot or Redux dispatch alone does not prove the save landed.
5. `get_eval_errors` diagnoses broken bindings; `get_render_health` / `check_layout` inspect
   rendered geometry. `capture_screenshot` verifies appearance and can scroll a target into view.

When the connection drops after a mutation, its outcome can be partial. Re-read the state
before retrying. Do not automatically repeat a write. A full page DSL export can be restored
with `import_page`, but it does not restore queries, JS objects, datasources or packages.
