import asyncio
import atexit
import json
import signal
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from appsmith_mcp.bidi import BiDiClient
from appsmith_mcp.defaults import (
    DATASOURCE_CONFIG_DEFAULTS,
    QUERY_ACTION_CONFIG_DEFAULTS,
)
from appsmith_mcp.utils import format_source, parse_function_names, pick
from appsmith_mcp.snippets import (
    ADD_WIDGETS_JS,
    BOOTSTRAP_JS,
    CHECK_LAYOUT_JS,
    CLEAR_CANVAS_JS,
    CREATE_APP_JS,
    CREATE_CUSTOM_WIDGET_JS,
    CREATE_DATASOURCES_JS,
    CREATE_JS_OBJECTS_JS,
    CREATE_PAGES_JS,
    CREATE_QUERIES_JS,
    DELETE_APP_JS,
    DELETE_CUSTOM_THEMES_JS,
    DELETE_DATASOURCES_JS,
    DELETE_JS_OBJECTS_JS,
    DELETE_PAGES_JS,
    DELETE_QUERIES_JS,
    DELETE_WIDGETS_JS,
    DUMP_STATE_JS,
    EXECUTE_JS_FUNCTIONS_JS,
    EXECUTE_QUERIES_JS,
    GET_CURRENT_THEME_JS,
    GET_JS_OBJECTS_JS,
    GET_WIDGET_JS,
    LIST_APPS_JS,
    LIST_DATASOURCES_JS,
    LIST_JS_OBJECTS_JS,
    LIST_PAGES_JS,
    LIST_PLUGINS_JS,
    LIST_QUERIES_JS,
    LIST_THEMES_JS,
    LIST_WORKSPACES_JS,
    LOG_METADATA_JS,
    MANAGE_TABLE_COLUMNS_JS,
    MANAGE_TABS_JS,
    PATCH_JS_OBJECTS_JS,
    PATCH_WIDGET_CODE_JS,
    RENAME_WIDGETS_JS,
    REPARENT_WIDGETS_JS,
    SAVE_CUSTOM_THEME_JS,
    SET_THEME_JS,
    SET_WIDGET_BOUNDS_JS,
    SUMMARY_JS,
    SWITCH_PAGE_JS,
    SYNC_WIDGET_SOURCE_JS,
    UPDATE_APP_JS,
    UPDATE_DATASOURCES_JS,
    UPDATE_JS_OBJECTS_JS,
    UPDATE_QUERIES_JS,
    UPDATE_THEME_JS,
    UPDATE_WIDGETS_JS,
)

mcp = FastMCP("appsmith-mcp")
client = BiDiClient()
ready = False

# Per-widget-type property schemas (defaults + configurable properties), dumped from Appsmith.
WIDGET_PROPS = json.loads((Path(__file__).parent / "widget_props.json").read_text())

WORKSPACE_FIELDS = ("id", "name")
APP_FIELDS = ("id", "name", "slug", "workspaceId", "defaultPageId", "editorUrl")
PAGE_FIELDS = ("id", "name", "isDefault", "isHidden", "slug", "isCurrent")
PLUGIN_FIELDS = ("id", "name", "packageName", "type")
DATASOURCE_FIELDS = ("id", "name", "pluginId", "workspaceId")
QUERY_FIELDS = ("id", "name", "pageId", "pluginId", "datasourceId", "httpMethod", "path")
JS_OBJECT_FIELDS = ("id", "name", "pageId", "actions")
LOG_FIELDS = ("category", "timestamp", "logType", "occurrenceCount", "sourceName", "sourceType")
CUSTOM_WIDGET_FIELDS = (
    "widgetId", "widgetName", "type", "srcDoc", "defaultModel", "events",
    "isVisible", "leftColumn", "topRow", "rightColumn", "bottomRow", "parentId",
)


async def ensure_ready():
    global ready
    try:
        await client.connect()
    except Exception:
        await client.reset()
        await client.connect()
    if ready:
        return
    for _ in range(30):
        try:
            ok = await client.run_snippet(BOOTSTRAP_JS)
        except Exception:
            await client.reset()
            await client.connect()
            ok = await client.run_snippet(BOOTSTRAP_JS)
        if ok:
            ready = True
            return
        await asyncio.sleep(1)
    raise RuntimeError("Could not find Redux store after 30s. Are you logged in and on an editor page?")


@mcp.tool()
async def get_state_summary() -> dict:
    """Return counts of widgets, datasources, and queries in the current Appsmith app."""
    await ensure_ready()
    raw = await client.run_snippet(SUMMARY_JS)
    widgets = raw.get("widgets", {}) if isinstance(raw, dict) else {}
    types = widgets.get("types") or []
    return {
        "widgets": {
            "count": int(widgets.get("count") or 0),
            "types": [t for t in types if isinstance(t, str)],
        },
        "datasources": int(raw.get("datasources") or 0) if isinstance(raw, dict) else 0,
        "queries": int(raw.get("queries") or 0) if isinstance(raw, dict) else 0,
    }


@mcp.tool()
async def list_workspaces() -> list:
    """List workspaces (id and name only)."""
    await ensure_ready()
    raw = await client.run_snippet(LIST_WORKSPACES_JS)
    return [pick(w, WORKSPACE_FIELDS) for w in (raw or []) if isinstance(w, dict)]


@mcp.tool()
async def list_apps() -> list:
    """List all applications across all workspaces with their editor URLs.
    Fetches via Appsmith's HTTP API, so it works from any page (dashboard or editor)."""
    await ensure_ready()
    raw = await client.run_snippet(LIST_APPS_JS)
    return [pick(a, APP_FIELDS) for a in (raw or []) if isinstance(a, dict)]


@mcp.tool()
async def create_app(name: str, workspace_id: str | None = None, icon: str = "bag", color: str = "#FFDEDE") -> dict:
    """Create a new Appsmith application. Uses the first workspace if workspace_id is omitted.
    On success Appsmith navigates to the new app's editor, so the Redux binding is reset."""
    global ready
    await ensure_ready()
    if not workspace_id:
        workspaces = await client.run_snippet(LIST_WORKSPACES_JS)
        if not workspaces:
            raise RuntimeError("No workspaces available. Navigate to the Appsmith dashboard first.")
        workspace_id = workspaces[0]["id"]
    raw = await client.run_snippet(
        CREATE_APP_JS,
        json_constants={
            "APP_NAME": name,
            "WORKSPACE_ID": workspace_id,
            "ICON": icon,
            "COLOR": color,
        },
    )
    ready = False
    return pick(raw, ("dispatched", "workspaceId", "name"))


@mcp.tool()
async def update_app(
    name: str | None = None,
    icon: str | None = None,
    color: str | None = None,
    navigation: dict | None = None,
    theme_settings: dict | None = None,
    positioning: dict | None = None,
    app_id: str | None = None,
) -> dict:
    """Update the current application's surface metadata and settings. `name`/`icon`/`color`
    rename or restyle. `navigation` patches `applicationDetail.navigationSetting` (e.g.
    `{"showNavbar": true, "orientation": "side", "navStyle": "sidebar", "colorStyle":
    "light", "showSignIn": true}`). `theme_settings` patches the app-wide sizing/density
    overrides (e.g. `{"sizing": 1.0, "density": 1.0, "appMaxWidth": "LARGE"}`).
    `positioning` patches the layout system (e.g. `{"type": "FIXED"}`). `app_id` defaults
    to the currently open application."""
    await ensure_ready()
    raw = await client.run_snippet(
        UPDATE_APP_JS,
        json_constants={
            "APP_ID": app_id,
            "NAME": name, "ICON": icon, "COLOR": color,
            "NAVIGATION": navigation or {},
            "THEME_SETTINGS": theme_settings or {},
            "POSITIONING": positioning or {},
        },
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def delete_app(app_id: str) -> dict:
    """Delete an application by id. The user is then redirected away from the editor."""
    await ensure_ready()
    raw = await client.run_snippet(
        DELETE_APP_JS,
        json_constants={"APP_ID": app_id},
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def get_logs(limit: int = 50) -> dict:
    """Return log/error metadata only — severity, category, timestamp, source name/type.
    Message text and payloads are intentionally excluded to avoid leaking confidential data."""
    await ensure_ready()
    raw = await client.run_snippet(
        LOG_METADATA_JS,
        json_constants={"SEVERITY": None, "LIMIT": int(limit)},
    )
    logs = (raw or {}).get("logs") or []
    raw_errors = (raw or {}).get("errors") or []
    info_entries = [e for e in logs if isinstance(e, dict) and e.get("severity") != "error"]
    error_entries = [e for e in logs if isinstance(e, dict) and e.get("severity") == "error"]
    error_entries.extend(e for e in raw_errors if isinstance(e, dict))
    return {
        "logs": [pick(e, LOG_FIELDS) for e in info_entries],
        "errors": [pick(e, LOG_FIELDS) for e in error_entries],
    }


@mcp.tool()
async def add_widgets(widgets: list[dict]) -> list:
    """Add multiple widgets in one tool call. Each entry is the same shape as `add_widget`'s
    args: `{widget_type, parent_id?, left?, top?, columns?, rows?, props?, name?, new_id?}`.
    `columns` and `rows` default to each widget type's own getDefaults() values. Returns a
    list of `{widgetId, widgetName, type, parent}` per widget, in the same order."""
    await ensure_ready()
    resolved = []
    for spec in widgets:
        defaults = WIDGET_PROPS.get(spec.get("widget_type"), {}).get("defaults", {})
        resolved.append({
            "widget_type": spec.get("widget_type"),
            "parent_id": spec.get("parent_id", "0"),
            "left": int(spec.get("left", 1)),
            "top": int(spec.get("top", 1)),
            "columns": int(spec.get("columns") if spec.get("columns") is not None else (defaults.get("columns") or 16)),
            "rows": int(spec.get("rows") if spec.get("rows") is not None else (defaults.get("rows") or 4)),
            "props": spec.get("props") or {},
            "name": spec.get("name"),
            "new_id": spec.get("new_id"),
        })
    raw = await client.run_snippet(
        ADD_WIDGETS_JS,
        json_constants={"WIDGETS": resolved},
        wait_for_save=True,
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def update_widgets(updates: list[dict]) -> list:
    """Apply property updates to one or more widgets. Each entry is
    `{"widget_id": <id>, "props": {<prop>: <value>, ...}}`.

    Dict values are deep-merged with existing state — so to change just one sub-key you
    can pass `{"srcDoc": {"css": "..."}}` without resending html/js. Non-dict values are
    replaced.

    Bindings and triggers are wired automatically:
      - properties whose name starts with `on` (e.g. `onClick`) are registered as triggers.
      - string values containing `{{...}}` are registered as dynamic bindings.
      - any other value is a literal and is removed from the dynamic path lists.

    Composite widgets (Statbox) and Modal show/hide are delegated automatically.
    Returns a list of per-widget results."""
    await ensure_ready()
    raw = await client.run_snippet(
        UPDATE_WIDGETS_JS,
        json_constants={"UPDATES": updates or []},
        wait_for_save=True,
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def delete_widgets(widget_ids: list[str]) -> list:
    """Delete multiple widgets in one tool call. Cascades children, disallowUndo is set."""
    await ensure_ready()
    raw = await client.run_snippet(
        DELETE_WIDGETS_JS,
        json_constants={"WIDGET_IDS": widget_ids or []},
        wait_for_save=True,
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def set_widget_bounds(updates: list[dict]) -> list:
    """Move and/or resize multiple widgets in one tool call. Each entry is
    `{"widget_id": <id>, "left": <int>, "top": <int>, "columns": <int>,
    "rows": <int>}` — `left`/`top` set the top-left, `columns`/`rows` set the
    size; any omitted field is preserved per widget. When `rows` is given,
    auto-height widgets are switched to FIXED so the resize sticks (reported as
    `heightModeOverridden`)."""
    await ensure_ready()
    raw = await client.run_snippet(
        SET_WIDGET_BOUNDS_JS,
        json_constants={"UPDATES": updates or []},
        wait_for_save=True,
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def rename_widgets(updates: list[dict]) -> list:
    """Rename multiple widgets in one tool call. Each entry is `{"widget_id": <id>,
    "new_name": <str>}`. New names must be valid Appsmith identifiers (alphanumeric,
    can't start with a digit, no spaces) — Appsmith may reject conflicts."""
    await ensure_ready()
    raw = await client.run_snippet(
        RENAME_WIDGETS_JS,
        json_constants={"UPDATES": updates or []},
        wait_for_save=True,
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def list_pages() -> list:
    """List all pages in the current application with id, name, default/hidden flags, and
    which is currently active."""
    await ensure_ready()
    raw = await client.run_snippet(LIST_PAGES_JS)
    return [pick(p, PAGE_FIELDS) for p in (raw or []) if isinstance(p, dict)]


@mcp.tool()
async def reparent_widgets(updates: list[dict]) -> list:
    """Reparent multiple widgets in one tool call. Each entry is `{"widget_id": <id>,
    "new_parent_id": <id>}`. The new parent must accept children (a CANVAS_WIDGET).
    Position is preserved verbatim — call set_widget_bounds afterwards if the
    new parent's snap dimensions differ."""
    await ensure_ready()
    raw = await client.run_snippet(
        REPARENT_WIDGETS_JS,
        json_constants={"UPDATES": updates or []},
        wait_for_save=True,
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def clear_canvas() -> dict:
    """Delete every widget directly under MainContainer. Cascades to nested children."""
    await ensure_ready()
    raw = await client.run_snippet(CLEAR_CANVAS_JS, wait_for_save=True)
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def get_widget(widget_id: str) -> dict:
    """Return the full Redux record for a widget — every property currently set,
    including position, type-specific config, and dynamic binding paths."""
    await ensure_ready()
    raw = await client.run_snippet(
        GET_WIDGET_JS,
        json_constants={"WIDGET_ID": widget_id},
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def check_layout() -> list:
    """Diagnose layout issues across every widget on the current page. For each widget
    returns its grid box, actual rendered pixel dimensions, and whether content overflows
    its container. For widgets with same-origin iframes (Custom, Iframe) also reports
    the inner body's scrollHeight so you can size to fit. Use to spot squashed or
    oversized widgets, then call resize_widget."""
    await ensure_ready()
    raw = await client.run_snippet(CHECK_LAYOUT_JS)
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def create_pages(names: list[str]) -> list:
    """Create multiple blank pages in the current application in one tool call."""
    await ensure_ready()
    raw = await client.run_snippet(
        CREATE_PAGES_JS,
        json_constants={"NAMES": names or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def delete_pages(page_ids: list[str]) -> list:
    """Delete multiple pages in one tool call."""
    await ensure_ready()
    raw = await client.run_snippet(
        DELETE_PAGES_JS,
        json_constants={"PAGE_IDS": page_ids or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def switch_page(page_id: str) -> dict:
    """Switch the editor to a different page in the current application."""
    await ensure_ready()
    raw = await client.run_snippet(
        SWITCH_PAGE_JS,
        json_constants={"PAGE_ID": page_id},
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def list_plugins() -> list:
    """List Appsmith plugins available to the current workspace (id, name, packageName, type).
    Use to find a pluginId for create_datasource — common ones: "REST API" (type: API),
    "PostgreSQL", "MongoDB", "MySQL" (type: DB)."""
    await ensure_ready()
    raw = await client.run_snippet(LIST_PLUGINS_JS)
    return [pick(p, PLUGIN_FIELDS) for p in (raw or []) if isinstance(p, dict)]


@mcp.tool()
async def list_datasources() -> list:
    """List datasources in the current workspace (id, name, pluginId, workspaceId).
    Use the id with create_query."""
    await ensure_ready()
    raw = await client.run_snippet(LIST_DATASOURCES_JS)
    return [pick(d, DATASOURCE_FIELDS) for d in (raw or []) if isinstance(d, dict)]


@mcp.tool()
async def list_queries() -> list:
    """List queries (a.k.a. actions) for the currently open application."""
    await ensure_ready()
    raw = await client.run_snippet(LIST_QUERIES_JS)
    return [pick(q, QUERY_FIELDS) for q in (raw or []) if isinstance(q, dict)]


@mcp.tool()
async def create_datasources(datasources: list[dict]) -> list:
    """Create multiple datasources in one tool call via Appsmith's REST API. Each entry is
    `{"name", "plugin_id", "url"?, "datasource_config"?, "workspace_id"?}`. If
    `datasource_config` is omitted, a per-plugin template is filled in (REST/GraphQL,
    Postgres/MySQL/Mongo) per entry's pluginPackageName. For REST you can pass just `url`.
    DB templates have empty host/port/credentials — populate them via `datasource_config`
    for a working connection. `workspace_id` defaults to the currently selected workspace.
    The Redux list is refetched once at the end."""
    await ensure_ready()
    raw = await client.run_snippet(
        CREATE_DATASOURCES_JS,
        json_constants={
            "DATASOURCES": datasources or [],
            "DEFAULTS": DATASOURCE_CONFIG_DEFAULTS,
        },
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def create_queries(queries: list[dict]) -> list:
    """Create multiple queries bound to datasources in one tool call via Appsmith's REST
    API. Each entry is `{"name", "datasource_id", "action_config"?, "page_id"?}`. If
    `action_config` is omitted, a per-plugin default is used: REST → GET / with empty
    headers/params; SQL DBs → `SELECT 1;`; Mongo → FIND with `{}` and limit 10. `page_id`
    defaults to the currently open page. The Redux action list is refetched once at the
    end."""
    await ensure_ready()
    raw = await client.run_snippet(
        CREATE_QUERIES_JS,
        json_constants={
            "QUERIES": queries or [],
            "DEFAULTS": QUERY_ACTION_CONFIG_DEFAULTS,
        },
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def update_queries(updates: list[dict]) -> list:
    """Update multiple queries in one tool call. Each entry is `{"query_id",
    "action_config"?, "name"?, "run_behaviour"?}`. `action_config` is shallow-merged into
    the existing actionConfiguration per entry, so you can change just `httpMethod` or
    `body` without re-sending the rest. The Redux action list is refetched once at the
    end."""
    await ensure_ready()
    raw = await client.run_snippet(
        UPDATE_QUERIES_JS,
        json_constants={"UPDATES": updates or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def execute_queries(query_ids: list[str]) -> list:
    """Run multiple queries by id and return their responses. Equivalent to clicking the
    Run button on each. Each result includes `{ok, statusCode, isExecutionSuccess, body}`."""
    await ensure_ready()
    raw = await client.run_snippet(
        EXECUTE_QUERIES_JS,
        json_constants={"ACTION_IDS": query_ids or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def delete_queries(query_ids: list[str]) -> list:
    """Delete multiple queries in one tool call."""
    await ensure_ready()
    raw = await client.run_snippet(
        DELETE_QUERIES_JS,
        json_constants={"ACTION_IDS": query_ids or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def update_datasources(updates: list[dict]) -> list:
    """Update multiple datasources in one tool call. Each entry is `{"datasource_id",
    "name"?, "datasource_config"?}`. `datasource_config` is shallow-merged into the
    current datasourceConfiguration across every environment storage per entry, so you
    can change just `url` or `authentication.password` without re-sending the whole
    config. The Redux datasource list is refetched once at the end."""
    await ensure_ready()
    raw = await client.run_snippet(
        UPDATE_DATASOURCES_JS,
        json_constants={"UPDATES": updates or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def delete_datasources(datasource_ids: list[str]) -> list:
    """Delete multiple datasources in one tool call."""
    await ensure_ready()
    raw = await client.run_snippet(
        DELETE_DATASOURCES_JS,
        json_constants={"DATASOURCE_IDS": datasource_ids or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def dump_state(verbose: bool = False) -> dict:
    """Return the state of the currently open Appsmith application.

    Always returns `url`, `application`, `pages`, and `widgets` (the canvas as a
    nested tree of id/name/type/parent/position/children starting at MainContainer).
    With `verbose=False` (default) that lightweight shape is all you get.

    Pass `verbose=True` to also carry every property set on each widget node, plus
    top-level `datasources` (with connection storage), `queries` (with their
    actionConfiguration), `jsObjects` (with their bodies), and a derived
    `connections` list mapping widget property/trigger paths to the queries/JS
    objects/datasources they bind to by name. This can be large for non-trivial
    apps."""
    await ensure_ready()
    raw = await client.run_snippet(DUMP_STATE_JS, json_constants={"VERBOSE": verbose})
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def list_themes() -> list:
    """List the themes available to the current application — built-in plus any saved
    custom themes. Each entry has id, name, displayName, and isSystemTheme."""
    await ensure_ready()
    raw = await client.run_snippet(LIST_THEMES_JS)
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def get_current_theme() -> dict:
    """Return the currently selected theme for the open application, including its
    `properties.{colors, fontFamily, borderRadius, boxShadow}` — the values widgets
    bind to via {{appsmith.theme.*}}."""
    await ensure_ready()
    raw = await client.run_snippet(GET_CURRENT_THEME_JS)
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def set_theme(theme_id: str) -> dict:
    """Switch the application to a different theme by id. Use list_themes to find ids."""
    await ensure_ready()
    raw = await client.run_snippet(
        SET_THEME_JS,
        json_constants={"THEME_ID": theme_id},
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def save_custom_theme(name: str) -> dict:
    """Save the current theme (with any local edits) as a named custom theme. The new
    theme appears in list_themes for future set_theme calls."""
    await ensure_ready()
    raw = await client.run_snippet(
        SAVE_CUSTOM_THEME_JS,
        json_constants={"NAME": name},
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def delete_custom_themes(themes: list[dict]) -> list:
    """Delete multiple saved custom themes in one tool call. Each entry is
    `{"theme_id", "name"?}`. `name` is looked up from the themes list per entry if
    omitted."""
    await ensure_ready()
    raw = await client.run_snippet(
        DELETE_CUSTOM_THEMES_JS,
        json_constants={"THEMES": themes or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def update_theme(properties: dict) -> dict:
    """Patch the current theme's properties. Pass a dict keyed by section
    (`colors`, `fontFamily`, `borderRadius`, `boxShadow`) whose values are dicts of
    keys to override. Example: {"colors": {"primaryColor": "#1a73e8"}, "fontFamily": {"appFont": "Inter"}}."""
    await ensure_ready()
    raw = await client.run_snippet(
        UPDATE_THEME_JS,
        json_constants={"PROPERTIES": properties or {}},
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def list_widget_types() -> list:
    """List every widget type for which a property schema is available."""
    return sorted(WIDGET_PROPS.keys())


@mcp.tool()
async def get_widget_schema(widget_type: str, property_name: str | None = None) -> dict:
    """Return the full property schema for a widget — defaults, meta properties, and
    every configurable property with its label, controlType, validation, options, and
    section. Use `property_name` to drill into a single property. Use the property
    names with update_widget."""
    schema = WIDGET_PROPS.get(widget_type)
    if schema is None:
        return {"error": f"unknown widget_type {widget_type}", "known": sorted(WIDGET_PROPS.keys())}
    if property_name is None:
        return schema
    prop = (schema.get("properties") or {}).get(property_name)
    if prop is None:
        return {
            "error": f"unknown property {property_name} on {widget_type}",
            "knownProperties": sorted((schema.get("properties") or {}).keys()),
        }
    return {"widgetType": widget_type, "property": property_name, **prop}


@mcp.tool()
async def manage_table_columns(
    widget_id: str,
    add: list | None = None,
    remove: list | None = None,
    reorder: list | None = None,
) -> dict:
    """Add, remove, or reorder columns on a TABLE_WIDGET_V2. Each `add` entry is
    `{"id": "<column_id>", "label"?: str, "columnType"?: "text"|"number"|"date"|"image"|...,
    "isDerived"?: bool}` — defaults match Appsmith's "+" button. `remove` is a list of
    column ids. `reorder` is the desired full list of column ids in order; ids not in
    the list keep their relative order at the end."""
    await ensure_ready()
    raw = await client.run_snippet(
        MANAGE_TABLE_COLUMNS_JS,
        json_constants={
            "WIDGET_ID": widget_id,
            "ADD": add or [],
            "REMOVE": remove or [],
            "REORDER": reorder or [],
        },
        wait_for_save=True,
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def manage_tabs(
    widget_id: str,
    add: list | None = None,
    remove: list | None = None,
    reorder: list | None = None,
) -> dict:
    """Add, remove, or reorder tabs on a TABS_WIDGET. Each `add` entry is `{"label"?: str}`
    — Appsmith generates the tab id and creates the child Canvas; if `label` is given
    it overrides the auto-generated "Tab N". `remove` is a list of tab ids. `reorder`
    is the desired full list of tab ids in order."""
    await ensure_ready()
    raw = await client.run_snippet(
        MANAGE_TABS_JS,
        json_constants={
            "WIDGET_ID": widget_id,
            "ADD": add or [],
            "REMOVE": remove or [],
            "REORDER": reorder or [],
        },
        wait_for_save=True,
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def list_js_objects() -> list:
    """List JS objects (collections) in the current application — id, name, pageId,
    and the function ids/names declared in each."""
    await ensure_ready()
    raw = await client.run_snippet(LIST_JS_OBJECTS_JS)
    return [pick(j, JS_OBJECT_FIELDS) for j in (raw or []) if isinstance(j, dict)]


@mcp.tool()
async def get_js_objects(js_object_ids: list[str] | None = None) -> list:
    """Return the full source of JS objects — each object's `body`, every
    function's `body`, and declared `variables`, plus id/name/pageId. Pass a list
    of ids to filter; omit it (or pass an empty list) to return them all."""
    await ensure_ready()
    raw = await client.run_snippet(
        GET_JS_OBJECTS_JS,
        json_constants={"IDS": js_object_ids or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def patch_js_objects(edits: list[dict]) -> list:
    """Make targeted string replacements in JS object bodies without rewriting them.

    Each edit is `{"target_id", "old", "new", "replace_all"?}` where `target_id`
    is a JS object id. `old` is matched literally; if it occurs more than once the
    edit fails unless `replace_all` is true (then every occurrence is replaced).

    Per-edit result reports `replacements` (count) or an `error` (target not
    found / `old` not found / ambiguous match)."""
    await ensure_ready()
    raw = await client.run_snippet(
        PATCH_JS_OBJECTS_JS,
        json_constants={"EDITS": edits or []},
        wait_for_save=True,
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def patch_widget_code(edits: list[dict]) -> list:
    """Make targeted string replacements in a Custom Widget's code without rewriting it.

    Each edit is `{"widget_id", "field", "old", "new", "replace_all"?}` where
    `field` is one of `html`, `css`, or `js`. `old` is matched literally; if it
    occurs more than once the edit fails unless `replace_all` is true (then every
    occurrence is replaced).

    Per-edit result reports `replacements` (count) or an `error` (widget not
    found / wrong type / bad field / `old` not found / ambiguous match). The change is
    written to both `srcDoc` and `uncompiledSrcDoc` so a reload can't revert it;
    successful edits report `synced: true`."""
    await ensure_ready()
    raw = await client.run_snippet(
        PATCH_WIDGET_CODE_JS,
        json_constants={"EDITS": edits or []},
    )
    if not isinstance(raw, dict):
        return []
    results = raw.get("results") or []
    updates = {}
    for fld in raw.get("fields") or []:
        updates.setdefault(fld["widget_id"], {})[fld["field"]] = format_source(fld["field"], fld["value"])
    if updates:
        await client.run_snippet(
            SYNC_WIDGET_SOURCE_JS,
            json_constants={"WIDGETS": [{"widget_id": wid, "srcDoc": sd} for wid, sd in updates.items()]},
            wait_for_save=True,
        )
        for r in results:
            if "error" not in r and r.get("widget_id") in updates:
                r["synced"] = True
    return results


@mcp.tool()
async def create_custom_widget(
    html: str | None = None,
    css: str | None = None,
    js: str | None = None,
    default_model: dict | str | None = None,
    name: str | None = None,
) -> dict:
    """Create a single Custom Widget — the primary entrypoint of this MCP.

    The widget is auto-sized to fill the main canvas: full width (all columns) and a
    height measured from the canvas's available pixel height. Size and position are not
    configurable. `html`/`css`/`js` seed its source; any omitted field falls back to
    Appsmith's starter template. `default_model` seeds the data the widget reads via
    `appsmith.model` (dict or JSON string). Seeded source is written to both `srcDoc` and
    `uncompiledSrcDoc` so a reload can't revert it (`synced: true`).
    Returns `{widgetId, widgetName, type, parent, columns, rows, measuredHeightPx, synced}`."""
    await ensure_ready()
    cw_defaults = WIDGET_PROPS.get("CUSTOM_WIDGET", {}).get("defaults", {})
    seed = html is not None or css is not None or js is not None
    src = dict(cw_defaults.get("srcDoc") or {})
    if html is not None:
        src["html"] = format_source("html", html)
    if css is not None:
        src["css"] = format_source("css", css)
    if js is not None:
        src["js"] = format_source("js", js)
    props = {}
    if default_model is not None:
        props["defaultModel"] = default_model if isinstance(default_model, str) else json.dumps(default_model)
    raw = await client.run_snippet(
        CREATE_CUSTOM_WIDGET_JS,
        json_constants={"PARENT_ID": "0", "PROPS": props, "NAME": name, "SRC": src, "SEED": seed},
        wait_for_save=True,
    )
    await client.run_snippet(
        SYNC_WIDGET_SOURCE_JS,
        json_constants={"WIDGETS": []},
        wait_for_save=True,
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def get_custom_widget(widget_id: str) -> dict:
    """Return a Custom Widget's full source (`srcDoc` html/css/js), `defaultModel`,
    events, name, and grid position. Errors if the id is not a CUSTOM_WIDGET."""
    await ensure_ready()
    raw = await client.run_snippet(GET_WIDGET_JS, json_constants={"WIDGET_ID": widget_id})
    if not isinstance(raw, dict):
        return {"raw": raw}
    if raw.get("type") != "CUSTOM_WIDGET":
        return {"error": f"widget {widget_id} is {raw.get('type')}, not a CUSTOM_WIDGET"}
    return pick(raw, CUSTOM_WIDGET_FIELDS)


@mcp.tool()
async def update_custom_widget(
    widget_id: str,
    default_model: dict | str | None = None,
    name: str | None = None,
    events: list[str] | None = None,
    triggers: dict | None = None,
    dynamic_height: str | None = None,
    left: int | None = None,
    top: int | None = None,
    columns: int | None = None,
    rows: int | None = None,
) -> dict:
    """Update a Custom Widget's model, name, events, triggers, height mode, and/or position.

    `default_model` replaces the model the widget reads via `appsmith.model` (dict or JSON
    string). `name` renames it. `events` registers the event names the widget can emit
    (e.g. `["onRefresh"]`). `triggers` binds those events to expressions, keyed by event
    name (e.g. `{"onRefresh": "{{ bootstrap.load() }}"}`) — each is wired into the widget's
    dynamicTriggerPathList automatically. `dynamic_height` is `"AUTO_HEIGHT"` or `"FIXED"`.
    `left`/`top`/`columns`/`rows` move/resize it. Source code (html/css/js) is not editable
    here — use patch_widget_code for targeted in-place source edits."""
    await ensure_ready()
    props = {}
    if default_model is not None:
        props["defaultModel"] = default_model if isinstance(default_model, str) else json.dumps(default_model)
    if events is not None:
        props["events"] = events
    if triggers:
        props.update(triggers)
    if dynamic_height is not None:
        props["dynamicHeight"] = dynamic_height
    result = {}
    if props:
        raw = await client.run_snippet(
            UPDATE_WIDGETS_JS,
            json_constants={"UPDATES": [{"widget_id": widget_id, "props": props}]},
            wait_for_save=True,
        )
        result["update"] = raw[0] if isinstance(raw, list) and raw else raw
        result["synced"] = True
    if name is not None:
        raw = await client.run_snippet(
            RENAME_WIDGETS_JS,
            json_constants={"UPDATES": [{"widget_id": widget_id, "new_name": name}]},
            wait_for_save=True,
        )
        result["rename"] = raw[0] if isinstance(raw, list) and raw else raw
    if any(v is not None for v in (left, top, columns, rows)):
        bounds = {"widget_id": widget_id}
        if left is not None:
            bounds["left"] = int(left)
        if top is not None:
            bounds["top"] = int(top)
        if columns is not None:
            bounds["columns"] = int(columns)
        if rows is not None:
            bounds["rows"] = int(rows)
        raw = await client.run_snippet(
            SET_WIDGET_BOUNDS_JS,
            json_constants={"UPDATES": [bounds]},
            wait_for_save=True,
        )
        result["bounds"] = raw[0] if isinstance(raw, list) and raw else raw
    if result:
        await client.run_snippet(
            SYNC_WIDGET_SOURCE_JS,
            json_constants={"WIDGETS": []},
            wait_for_save=True,
        )
        result["synced"] = True
    return result or {"noop": True}


@mcp.tool()
async def delete_custom_widget(widget_id: str) -> dict:
    """Delete a Custom Widget by id."""
    await ensure_ready()
    raw = await client.run_snippet(
        DELETE_WIDGETS_JS,
        json_constants={"WIDGET_IDS": [widget_id]},
        wait_for_save=True,
    )
    await client.run_snippet(
        SYNC_WIDGET_SOURCE_JS,
        json_constants={"WIDGETS": []},
        wait_for_save=True,
    )
    result = raw[0] if isinstance(raw, list) and raw else {"raw": raw}
    if isinstance(result, dict):
        result["synced"] = True
    return result


@mcp.tool()
async def create_js_objects(objects: list[dict]) -> list:
    """Create multiple JS objects in one tool call. Each entry is `{"name", "body",
    "function_names"?, "page_id"?}`. `body` is the full source (e.g.
    `export default { foo: () => 1, bar: () => 2 }`). If `function_names` is omitted,
    the top-level function names in `body` are parsed automatically per entry. `page_id`
    defaults to the currently open page."""
    await ensure_ready()
    resolved = []
    for o in objects or []:
        body = o.get("body", "")
        function_names = o.get("function_names")
        names = function_names if function_names is not None else parse_function_names(body)
        resolved.append({
            "name": o.get("name"),
            "body": body,
            "function_names": names,
            "page_id": o.get("page_id"),
        })
    raw = await client.run_snippet(
        CREATE_JS_OBJECTS_JS,
        json_constants={"OBJECTS": resolved},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def delete_js_objects(js_object_ids: list[str]) -> list:
    """Delete multiple JS objects in one tool call."""
    await ensure_ready()
    raw = await client.run_snippet(
        DELETE_JS_OBJECTS_JS,
        json_constants={"COLLECTION_IDS": js_object_ids or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def update_js_objects(updates: list[dict]) -> list:
    """Replace the source of multiple JS objects in one tool call. Each entry is
    `{"js_object_id", "body"}`. Function names are re-parsed by Appsmith from each body."""
    await ensure_ready()
    raw = await client.run_snippet(
        UPDATE_JS_OBJECTS_JS,
        json_constants={"UPDATES": updates or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def execute_js_functions(executions: list[dict]) -> list:
    """Execute multiple JS functions in one tool call. Each entry is `{"js_object_id",
    "function_name"}`. Returns each result if the eval tree captured it; otherwise
    reports that the dispatch fired but no value surfaced (function may still have run
    for its side effects)."""
    await ensure_ready()
    raw = await client.run_snippet(
        EXECUTE_JS_FUNCTIONS_JS,
        json_constants={"EXECUTIONS": executions or []},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def run_command(snippet: str) -> dict:
    """Evaluate an arbitrary JS snippet in the attached Firefox tab and return the result.
    The snippet runs in page context with access to `window.__store`. Use for exploring
    Redux state and discovering action shapes. Result must be JSON-serializable. Use
    sparingly and only with explicit user permission — this is an escape hatch that can
    dispatch any action and read any state, bypassing the safety constraints of the
    other tools."""
    await ensure_ready()
    result = await client.run_snippet(snippet)
    return {"result": result}


@mcp.tool()
async def get_url() -> dict:
    """Return the URL currently loaded in the attached Firefox tab — e.g. the dashboard
    `/applications`, an app editor `/app/<slug>/page1-<id>/edit`, or elsewhere."""
    await ensure_ready()
    return {"url": await client.get_url()}


@mcp.tool()
async def navigate(url: str) -> dict:
    """Navigate the attached Firefox tab to a URL. Resets the Redux store binding."""
    global ready
    await ensure_ready()
    await client.navigate(url)
    ready = False
    return {"navigated": url}


@mcp.tool()
async def refresh_page() -> dict:
    """Reload the attached Firefox tab (same URL) and wait for it to finish loading.
    Resets the Redux store binding, so the next tool call re-bootstraps it."""
    global ready
    await ensure_ready()
    await client.reload()
    ready = False
    return {"reloaded": await client.get_url()}


def main():
    atexit.register(_shutdown)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: (_shutdown(), exit(0)))
        except Exception:
            pass
    mcp.run()


def _shutdown():
    if client.ws is None:
        return
    try:
        asyncio.run(client.close())
    except Exception:
        pass


if __name__ == "__main__":
    main()
