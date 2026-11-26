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

The tools cover the full editor surface but lean toward **custom widgets** —
self-contained HTML/CSS/JS components — since AI is generally better at building a UI as
code than by arranging Appsmith's native widgets on a visual grid.

## Prerequisites

- **Firefox** — the server attaches to a running instance.
- **Python 3.10+** and [uv](https://docs.astral.sh/uv/).
- A reachable Appsmith instance you can log into.

## Install

```sh
uv sync
```

## Launch Firefox with remote debugging

```sh
./launch.sh
```

This starts Firefox with the BiDi remote-debugging port enabled (works on macOS, Linux,
and Windows via Git Bash). Log into Appsmith and navigate to an app's editor page
(`.../edit`) in that window. The server re-bootstraps on the next tool call after any
navigation.

### Multiple isolated instances

To run more than one Appsmith session at a time, give each Firefox instance its own
port and persistent profile:

```sh
./launch.sh 9222 appsmith-dev
./launch.sh 9223 appsmith-staging
```

Profiles are stored under `.firefox-profiles/<profile>` and are ignored by Git. Each one
keeps its own Firefox data and Appsmith login. If no profile is given, `default` is used.
The launcher never closes other Firefox windows.

The matching MCP server process must use the same port. Set
`APPSMITH_BIDI_PORT=9223` before starting the second server on macOS/Linux, or in
PowerShell:

```powershell
$env:APPSMITH_BIDI_PORT = "9223"
```

The optional first argument to `launch.sh` overrides `APPSMITH_BIDI_PORT` for
Firefox.

## Register with Claude Code

```sh
claude mcp add --scope user appsmith /path/to/appsmith-mcp/.venv/bin/appsmith-mcp
```

After launching/relaunching Firefox, reconnect the server with `/mcp` so it re-attaches.

## Tools

**App & workspace**

- `list_workspaces` — List workspaces (id and name).
- `list_apps` — List all applications across workspaces, with editor URLs.
- `create_app` — Create a new application.
- `update_app` — Update the current app's metadata and settings (name, navigation, theme, layout).
- `delete_app` — Delete an application by id.
- `get_state_summary` — Counts of widgets, datasources, and queries in the current app.
- `dump_state` — Dump the current app's pages and widget tree (optionally full detail).
- `get_logs` — Return log/error metadata (no message text).

**Pages**

- `list_pages` — List the app's pages, flags, and which is active.
- `create_pages` — Create one or more blank pages.
- `delete_pages` — Delete one or more pages.
- `switch_page` — Switch the editor to another page.

**Custom widgets**

- `create_custom_widget` — Create a self-contained HTML/CSS/JS widget (the primary entrypoint).
- `get_custom_widget` — Return a custom widget's source, model, events, name, and position.
- `update_custom_widget` — Update its model, name, events, triggers, height mode, or position.
- `delete_custom_widget` — Delete a custom widget by id.
- `patch_widget_code` — Make targeted edits to a custom widget's source without rewriting it.

**Widgets (native)**

- `add_widgets` — Add one or more native widgets.
- `update_widgets` — Apply property updates to one or more widgets.
- `delete_widgets` — Delete one or more widgets (cascades children).
- `set_widget_bounds` — Move and/or resize widgets.
- `rename_widgets` — Rename widgets.
- `reparent_widgets` — Move widgets to a new parent canvas.
- `clear_canvas` — Delete every widget on the page.
- `get_widget` — Return a widget's full Redux record.
- `check_layout` — Diagnose layout/overflow issues across the page.
- `list_widget_types` — List widget types with a known property schema.
- `get_widget_schema` — Return a widget type's property schema (controls, validation, defaults).
- `manage_table_columns` — Add, remove, or reorder columns on a table widget.
- `manage_tabs` — Add, remove, or reorder tabs on a tabs widget.

**JS objects**

- `list_js_objects` — List JS objects with their declared function names.
- `get_js_objects` — Return full source of JS objects (bodies, functions, variables).
- `create_js_objects` — Create one or more JS objects.
- `update_js_objects` — Replace the source of one or more JS objects.
- `delete_js_objects` — Delete one or more JS objects.
- `patch_js_objects` — Make targeted edits to JS object bodies without rewriting them.
- `execute_js_functions` — Run JS object functions and return their results. Blocked unless
  unsafe execution is enabled (see [Execution policy](#execution-policy)).

**Queries**

- `list_queries` — List the app's queries (datasource actions).
- `create_queries` — Create one or more queries bound to datasources.
- `update_queries` — Update one or more queries.
- `delete_queries` — Delete one or more queries.
- `execute_queries` — Run read-only queries by id and return their responses (see
  [Execution policy](#execution-policy)).

**Datasources**

- `list_datasources` — List datasources in the current workspace.
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
- `refresh_page` — Reload the tab and wait for it to finish.
- `run_command` — Evaluate arbitrary JS in the tab and return the result. Blocked unless
  unsafe execution is enabled (see [Execution policy](#execution-policy)).

> **⚠️ `run_command`** evaluates arbitrary JavaScript in the attached browser tab with full
> access to the Redux store and the page — it can read or modify anything in the live
> session, bypassing the safety constraints of the other tools. It's an escape hatch for
> exploring state and discovering action shapes; use it deliberately.

## Execution policy

`execute_queries` runs a query only after a fail-closed, read-only check of its saved
configuration. Anything the policy cannot classify as a read is returned with
`blocked: true` and is never sent to Appsmith:

- **SQL** (MSSQL, MySQL, Oracle, Postgres, Redshift, Snowflake): a single `SELECT` or
  `WITH ... SELECT`, with no write or administrative keyword (`INSERT`, `UPDATE`, `DELETE`,
  `MERGE`, `EXEC`, `INTO`, `SET`, DDL, ...). Text that the engines' lexical rules could read
  differently (backslash escapes, nested comments, `#` comments, dollar quoting) must be a
  single read under every interpretation, and unterminated literals or comments are blocked.
- **REST API**: `GET` and `HEAD` only.
- **GraphQL**: queries only; mutations and subscriptions are blocked.
- **MongoDB**: `FIND`, `COUNT`, `DISTINCT`, and `AGGREGATE` without `$out` or `$merge`.
- **Any other plugin**: blocked.

The check is **best-effort static analysis, not a guarantee**. It cannot tell what a database
function or HTTP endpoint does when called (for example `SELECT pg_terminate_backend(...)`
or a `GET` endpoint with side effects), and it inspects the saved text before Appsmith
evaluates `{{ }}` bindings. Keep database and API permissions as the real boundary: give the
datasources a read-only account wherever possible.

`run_command` and `execute_js_functions` can bypass this policy (arbitrary JavaScript can
call the execution API directly, and a JS function can run any query), so they are blocked
by default. To allow them, start the MCP server with `APPSMITH_ALLOW_UNSAFE_EXECUTION=1`
(`true` and `yes` also work). Like `APPSMITH_BIDI_PORT`, it applies per server process,
so one instance can allow them while another stays read-only.

## License

[MIT](LICENSE)
