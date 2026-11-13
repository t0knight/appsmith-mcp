# appsmith-mcp

An MCP server that lets an AI agent control [Appsmith](https://www.appsmith.com/) — building
and editing apps (pages, widgets, queries, datasources, JS objects, themes) by driving the
real editor in the browser. It attaches to a running Firefox over the
[WebDriver BiDi](https://w3c.github.io/webdriver-bidi/) protocol and reads/dispatches the
editor's Redux store, so an agent can operate Appsmith the same way a person would.

## How it works

Appsmith has no public API for editing apps — the builder lives entirely in the browser.
This server drives that builder in place: it attaches to a running Firefox over WebDriver
BiDi, finds Appsmith's Redux store on the open editor page, and runs predefined JavaScript
snippets against it.

Each tool is one such snippet. Reads pull straight from Redux state; writes dispatch the
same actions the editor UI fires when you click — so creating a widget, wiring a query, or
editing a custom widget's source is the programmatic equivalent of doing it by hand, and
changes render live and save to the Appsmith backend.

The tools cover the full editor surface and favour building screens the way a person
would in the editor — **native widgets** with data picked in the property pane, properties
stored exactly as the pane stores them (bindings, triggers and the "JS" toggle), queries that
run only when needed — so whoever maintains the app can read and edit it in the editor. Custom
widgets are there for what native widgets can't render. Package modules (code and UI) can be
edited, published and used on pages too.

## Prerequisites

- **Firefox** — the server attaches to a running instance.
- **Python 3.10+** and [uv](https://docs.astral.sh/uv/) or `pip`.
- A reachable Appsmith instance you can log into.

## Install

**uv:**

```sh
uv sync
```

**pip:**

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Launch Firefox with remote debugging

```sh
./launch.sh
```

This kills any running Firefox and reopens it with the BiDi port enabled (works on macOS,
Linux, and Windows via Git Bash). Log into Appsmith and navigate to an app's editor page
(`.../edit`) in that window. The server re-bootstraps on the next tool call after any
navigation.

> **Auto-login (opcional):** para instâncias com login por email+senha, `login.py` sobe o
> Firefox e faz login sozinho lendo um `.env`, dispensando o login manual. Veja
> [AUTO-LOGIN.md](AUTO-LOGIN.md).

## Register with Claude Code

```sh
claude mcp add --scope user appsmith /path/to/appsmith-mcp/.venv/bin/appsmith-mcp
```

After launching/relaunching Firefox, reconnect the server with `/mcp` so it re-attaches.

## Tools

**Discovery (works without Firefox)**

- `get_capabilities` — Registered tools, package version and execution policy; runtime
  availability stays unverified until `get_build_context` inspects the editor.
- `get_guide` — List bundled recipes, or read one by slug (`reading-state`, `diagnostics`,
  `download-binary`, etc.). Recipes are included in installed packages.

Every tool has explicit MCP effect annotations. They describe behavior to the client;
execution restrictions are enforced separately. Previews/navigation can change runtime
state, and exporting to a file can overwrite a local file.

`configure_table` and `set_validation` accept their documented named options/rules over MCP.
Omitted/None values leave properties unchanged; false, zero and empty strings are written.
They return `ok`/`persisted` only after a confirmed save, and raise on save failure.
`set_widget_events` reports persistence per event for mixed-success batches and raises when
every target failed. Repeated widget/event pairs use the last value and report it once.
Reconnect/restart the MCP process after updating to reload its catalog.

**App & workspace**

- `list_workspaces` — List workspaces (id and name).
- `list_apps` — List all applications across workspaces, with editor URLs.
- `create_app` — Create a new application.
- `update_app` — Update the current app's metadata and settings (name, navigation, theme, layout).
- `delete_app` — Delete an application by id.
- `get_state_summary` — Counts of widgets, datasources, and queries in the current app.
- `get_store` — Read `appsmith.store`, optionally by key, with token/password/secret values masked.
- `eval_value` — Read one already-evaluated data-tree path without evaluating arbitrary code.
- `dump_state` — Dump the current app's pages and widget tree (optionally full detail, or scoped with `sections`).
- `get_logs` — Return log/error metadata; `include_messages=true` adds the error text.
- `get_eval_errors` — Return the editor's evaluation ("red") errors from the dataTree, with messages.
- `capture_screenshot` — PNG of the tab (viewport, one widget cropped, `scroll_to`, or `full_page`); `screenshot` is the no-argument alias.
- `set_store` — Write `appsmith.store` values the way `storeValue` does (UI state only).
- `get_render_health` — Compare the DSL against the DOM after the page settles; split genuine `problems` from `expected` by-design absences (closed modals, inactive tabs).
- `lint_design` — Read-only design lint: missing labels, raw column names, visible id columns, hardcoded colors, stale `<query>.data` in modals, misaligned rows/gaps.
- `preview_hidden` — Screenshot an inactive tab or a closed modal, restoring the original state afterward.

**Pages**

- `list_pages` — List the app's pages, flags, and which is active.
- `create_pages` — Create one or more blank pages.
- `delete_pages` — Delete one or more pages.
- `switch_page` — Switch the editor to another page and wait until it is actually rendered.
- `get_build_context` — Report the selected vs rendered page and whether they are consistent (preflight before mutating).
- `export_page` — Snapshot a page's full DSL as JSON (or `save_to_path` to a file / `summary` for a light tree).
- `import_page` — Restore a page from an `export_page` snapshot (`dsl` or `from_path`).

**Custom widgets**

- `create_custom_widget` — Create a self-contained HTML/CSS/JS widget (only when native widgets can't do it).
- `get_custom_widget` — Return a custom widget's source, model, events, name, and position.
- `update_custom_widget` — Update its model, name, events, triggers, height mode, or position.
- `delete_custom_widget` — Delete a custom widget by id.
- `set_custom_widget_code` — Replace whole html/css/js fields on one or more custom widgets.
- `sync_custom_widget` — Copy one custom widget's source/model/events onto others.
- `patch_widget_code` — Make targeted edits to a custom widget's source; literal matching is
  preferred, with a unique whitespace-normalized fallback for formatter differences.

**Widgets (native)**

- `add_widgets` — Add one or more native widgets (same property policy as `update_widgets`; geometry in `props` is refused; warns on overlap; rewires a modal's close buttons to its real name).
- `update_widgets` — Apply **configuration** property updates; bindings/triggers registered and the pane's "JS" toggle set where the control can't show a binding; layout/structure props are refused; `check_eval` surfaces newly introduced eval errors.
- `connect_widget_data` — Connect a table/select to a query (or a package query instance) like the Data dropdown; tables get editor-style columns (labels, types, BRL/date formats). A sample is only run when the query passes the read-only policy.
- `delete_widgets` — Delete one or more widgets (cascades children).
- `set_widget_bounds` — Move and/or resize widgets (reports the *effective* box after relayout, and `moved`).
- `rename_widgets` — Rename widgets.
- `reparent_widgets` — Move widgets to a new parent canvas.
- `clear_canvas` — Delete every widget on the page.
- `list_widgets` — Light flat map of every widget (name/id/type/parent/box) — the cheap discovery read.
- `list_children` — List only a widget/canvas's direct children, including default modal children.
- `find_widgets` — Grep the page's widgets by type, property value and/or parent.
- `get_widget_style` / `get_page_background` — A widget's resolved style block; the effective page background.
- `list_icon_names` — Valid Blueprint `iconName` values for native widgets.
- `get_widget` — Return a widget's full Redux record (by id **or name**; `fields`/`include_source` to trim it).
- `check_layout` — Diagnose layout/overflow issues across the page.
- `list_widget_types` — List widget types with a known property schema.
- `get_widget_schema` — Return a widget type's property schema (controls, validation, defaults).
- `manage_table_columns` — Add, remove, reorder, configure or seed table columns (labels, widths, currency/decimals, date formats, `editable`); builds ROW_LEVEL `editActions` columns.
- `manage_tabs` — Add, remove, or reorder tabs on a tabs widget.
- `reset_widget_tree` — Build the ready-to-paste JS that resets a container's whole subtree (and closes it, if a modal).

**Run behaviour**

- `set_page_load_actions` — Turn queries' on-page-load on/off and recompute the page's on-load set.
- `set_run_behaviour` — Manual / On page load / Automatic for queries and JS functions (Automatic requires a `reason`).

**Packages & modules**

- `list_packages` / `get_package` — Code (query/JS modules) and UI packages, modules, inputs/outputs.
- `create_package` / `create_modules` — Create packages and QUERY / JS / UI modules.
- `open_module` — Open a module in the editor; the regular tools then work on it (queries, JS, widgets).
- `update_module` — Module inputs, outputs and name.
- `publish_package` — Publish a new version (requires `confirm=True`).
- `list_module_instances` / `add_module_instances` / `update_module_instances` / `delete_module_instances` — Module instances on the current page (inputs, UI module widgets).
- `run_module_instances` — Run query-module instances natively (same read-only policy as `execute_queries`).
- `update_app_packages` — Bring the app's instances to the latest published versions.

**JS objects**

- `list_js_objects` — List JS objects with their declared function names.
- `get_js_objects` — Return full source of JS objects (bodies, functions, variables).
- `create_js_objects` — Create one or more JS objects.
- `update_js_objects` — Replace the source of one or more JS objects.
- `delete_js_objects` — Delete one or more JS objects.
- `patch_js_objects` — Make targeted edits to JS object bodies without rewriting them.
- `execute_js_functions` — Disabled by the read-only policy because JS functions can
  indirectly execute mutations and other side effects.

**Queries**

- `list_queries` — List the app's queries (datasource actions).
- `get_queries` — Return queries' full `actionConfiguration`; literal Authorization/API-key
  header values are masked while binding expressions remain visible.
- `create_queries` — Create queries and auto-register every `{{...}}` path in
  `dynamicBindingPathList`; literal sensitive auth headers are refused.
- `update_queries` — Update queries and rebuild bindings from the merged configuration;
  literal sensitive auth headers are refused.
- `delete_queries` — Delete one or more queries.
- `execute_queries` — Run only actions classified as read-only, resolving `{{...}}`
  bindings like the Run button. Allows one SQL `SELECT`/`WITH ... SELECT`, REST GET/HEAD,
  GraphQL queries, and MongoDB FIND/COUNT/DISTINCT/AGGREGATE without `$out` or `$merge`.
  Everything else fails closed with `blocked=true` and is not dispatched.

**Datasources**

- `list_datasources` — List datasources in the current workspace.
- `get_datasource` — Return effective per-environment configuration with secrets masked in-browser.
- `create_datasources` — Create one or more datasources.
- `update_datasources` — Update one or more datasources.
- `delete_datasources` — Delete one or more datasources.
- `list_plugins` — List available plugins (REST, Postgres, MongoDB, etc.).

**Themes**

- `list_themes` — List built-in and saved custom themes.
- `get_current_theme` — Return the active theme and its color/font/radius/shadow values.
- `set_theme` — Switch the app to a theme by id.
- `update_theme` — Patch the current theme's properties.
- `save_custom_theme` — Save the current theme as a named custom theme.
- `delete_custom_themes` — Delete saved custom themes.

**Browser & navigation**

- `get_url` — Return the URL loaded in the attached Firefox tab.
- `navigate` — Navigate the tab to a URL.
- `refresh_page` — Reload the tab (dropping any selected-entity URL segment) and wait for the page to settle.
- `run_command` — Disabled by the read-only policy.

> **Read-only execution policy:** the MCP never dispatches SQL writes, stored procedures,
> multiple SQL statements, REST writes, GraphQL mutations, or MongoDB writes. Unknown or
> ambiguous actions are blocked. Arbitrary JavaScript and JS-object execution are disabled
> because either could bypass this policy. Query and JS editing tools remain available.

## Guard rails

`update_widgets` persists by rewriting the page DSL, so it used to accept any property —
including the ones the layout engine derives. Writing `bottomRow` or a hand-built
`primaryColumns` produced a state the editor could never create; the failure then surfaced
on the *next* page load, as a blank widget or a page that would not open, with `errors: []`
in the debugger and no way to roll back.

So the write path is now typed by ownership:

| You want to change | Use |
|---|---|
| position, size, height mode | `set_widget_bounds` |
| table columns | `manage_table_columns` |
| tabs | `manage_tabs` |
| widget name | `rename_widgets` |
| parent canvas | `reparent_widgets` |
| anything else | `update_widgets` |

`update_widgets` refuses the rest and names the tool that owns it. It also checks property
names against the widget's own schema, so `labelText` on an `INPUT_WIDGET_V2` — whose
property is `label` — is auto-normalized (the correct name is unambiguous), and a genuine
typo is refused with the correction rather than stored somewhere nothing reads. Table columns
are configured with the dotted path `primaryColumns.<col>.<prop>`, validated against the real
column sub-schema (no more false "not in the known schema" per column property).

Two independent escape hatches, so you never reach for the dangerous one to clear a harmless
schema gap: `allow_unknown_props=true` downgrades unknown-property typos to warnings but still
refuses owned properties; `force=true` overrides everything, including the owned-property
refusals, and can corrupt the page.

Two habits the tools now support:

- **Snapshot before a risky batch.** `export_page` → JSON, `import_page` to roll back.
- **Verify before claiming done.** Redux holding 55 widgets is not the same as 55 widgets
  rendering. `get_render_health` waits for the page to settle, then compares the DSL against
  the DOM and names what is genuinely broken — keeping by-design absences (closed modals,
  inactive tabs) in a separate `expected` list; `screenshot` shows the result.

## Persistence and page routing

Widget mutations dispatch into the client Redux store and rely on a debounced autosave that
often never lands. Every mutator (`add_widgets`, `delete_widgets`, `set_widget_bounds`,
`rename_widgets`, `reparent_widgets`, `clear_canvas`, `update_widgets`) therefore finishes
with an explicit layout `PUT` and reports `persisted: true` only on an HTTP 2xx — a plain
dispatch is never treated as proof.

That `PUT` is refused when the *selected* page (where the write lands) is not the *rendered*
page (whose widgets are in the store); persisting in that split state would overwrite the
wrong page. `switch_page` waits until both converge before returning, and `get_build_context`
lets you check `consistent` before a cross-page batch.

## License

[MIT](LICENSE)
