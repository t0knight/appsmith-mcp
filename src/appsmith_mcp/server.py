import asyncio
import atexit
import base64
import json
import re
import signal
from collections import defaultdict, deque
from pathlib import Path

from mcp.server.fastmcp import Image
from typing import Literal

from appsmith_mcp.protocol import AppsmithMCP
from appsmith_mcp.discovery import build_capabilities, read_guide

from appsmith_mcp.bidi import BiDiClient
from appsmith_mcp.defaults import (
    DATASOURCE_CONFIG_DEFAULTS,
    QUERY_ACTION_CONFIG_DEFAULTS,
)
from appsmith_mcp.execution_policy import assess_query_action
from appsmith_mcp.icons import BLUEPRINT_ICON_NAMES, find_icon_names
from appsmith_mcp.query_configuration import prepare_action_configuration
from appsmith_mcp.panel_policy import validate_panel_writes
from appsmith_mcp.widget_events import build_action
from appsmith_mcp.utils import format_source, parse_function_names, pick
from appsmith_mcp.validation import (
    _known_props,
    format_problems,
    resolve_label_synonyms,
    side_effect_notes,
    validate_new_widget_props,
    validate_widget_updates,
)
from appsmith_mcp.snippets import (
    ADD_WIDGETS_JS,
    DESCRIBE_WIDGETS_JS,
    EXPORT_PAGE_JS,
    IMPORT_PAGE_JS,
    INSPECT_STATE_JS,
    LIST_WIDGETS_JS,
    RENDER_HEALTH_JS,
    RUN_ACTIONS_JS,
    SET_DEFAULT_TAB_JS,
    SETTLE_JS,
    TOGGLE_MODAL_JS,
    BOOTSTRAP_JS,
    CHECK_LAYOUT_JS,
    CLEAR_CANVAS_JS,
    CONNECT_WIDGET_DATA_JS,
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
    EXECUTE_QUERIES_JS,
    SET_PAGE_LOAD_ACTIONS_JS,
    SET_RUN_BEHAVIOUR_JS,
    FIND_WIDGETS_JS,
    GET_BUILD_CONTEXT_JS,
    GET_PAGE_BACKGROUND_JS,
    GET_WIDGET_STYLE_JS,
    SET_STORE_JS,
    GET_CURRENT_THEME_JS,
    GET_EVAL_ERRORS_JS,
    GET_JS_OBJECTS_JS,
    GET_QUERIES_JS,
    GET_WIDGET_JS,
    LIST_APPS_JS,
    LIST_DATASOURCES_JS,
    LIST_JS_OBJECTS_JS,
    LIST_PAGES_JS,
    LIST_PLUGINS_JS,
    LIST_QUERIES_JS,
    LIST_THEMES_JS,
    LIST_WORKSPACES_JS,
    LINT_DESIGN_JS,
    LOG_METADATA_JS,
    MANAGE_TABLE_COLUMNS_JS,
    MANAGE_TABS_JS,
    PATCH_JS_OBJECTS_JS,
    PATCH_WIDGET_CODE_JS,
    PERSIST_LAYOUT_JS,
    PACKAGES_JS,
    MODULE_INSTANCES_JS,
    PROPERTY_POLICY_JS,
    RENAME_WIDGETS_JS,
    RESET_WIDGET_TREE_JS,
    REPARENT_WIDGETS_JS,
    SCROLL_WIDGET_JS,
    SAVE_CUSTOM_THEME_JS,
    SET_THEME_JS,
    SET_WIDGET_BOUNDS_JS,
    SUMMARY_JS,
    SWITCH_PAGE_JS,
    SYNC_CUSTOM_WIDGET_JS,
    SYNC_WIDGET_SOURCE_JS,
    UPDATE_APP_JS,
    UPDATE_DATASOURCES_JS,
    UPDATE_JS_OBJECTS_JS,
    UPDATE_QUERIES_JS,
    UPDATE_THEME_JS,
    UPDATE_WIDGETS_JS,
)

mcp = AppsmithMCP("appsmith-mcp")
client = BiDiClient()
ready = False

# Injected (raw JS) into widget-mutation snippets so they can `await __persistLayout({overrides,
# removedIds})` — the shared, honest layout-PUT that replaces the debounced autosave.
PERSIST = {"__persistLayout": PERSIST_LAYOUT_JS}

# Per-widget-type property schemas (defaults + configurable properties), dumped from Appsmith.
WIDGET_PROPS = json.loads((Path(__file__).parent / "widget_props.json").read_text())


def _prop(control, section, *, trigger=False, help_text=None):
    p = {"configType": "content", "controlType": control, "section": section,
         "isBindProperty": True, "isTriggerProperty": trigger}
    if help_text:
        p["helpText"] = help_text
    return p


# The dump captured each widget's OWN property-pane config but not the properties it inherits
# via `__spreads__: [<spread: BaseInputWidget.getDefaults()>]` — so INPUT_WIDGET_V2 etc. lost
# `label`, `placeholderText`, `tooltip` and the label-layout props. Re-add them so
# get_widget_schema is complete and callers stop guessing (feedback items 4/5).
BASE_INPUT_WIDGET_PROPERTIES = {
    "label": _prop("INPUT_TEXT", "Label", help_text="Sets the label text of the widget"),
    "labelPosition": _prop("ICON_TABS", "Label"),
    "labelAlignment": _prop("LABEL_ALIGNMENT_OPTIONS", "Label"),
    "labelWidth": _prop("NUMERIC_INPUT", "Label"),
    "tooltip": _prop("INPUT_TEXT", "Label", help_text="Adds a tooltip (help icon) next to the label"),
    "placeholderText": _prop("INPUT_TEXT", "Data", help_text="Sets a placeholder to show when the input is empty"),
    "isSpellCheck": _prop("SWITCH", "Validation"),
    "shouldAllowAutofill": _prop("SWITCH", "General"),
    "autoFocus": _prop("SWITCH", "General"),
    "resetOnSubmit": _prop("SWITCH", "General"),
    "onTextChanged": _prop("ACTION_SELECTOR", "Events", trigger=True),
    "onSubmit": _prop("ACTION_SELECTOR", "Events", trigger=True),
    "onFocus": _prop("ACTION_SELECTOR", "Events", trigger=True),
    "onBlur": _prop("ACTION_SELECTOR", "Events", trigger=True),
}
for _t, _schema in WIDGET_PROPS.items():
    _spreads = ((_schema.get("defaults") or {}).get("__spreads__")) or []
    if any("BaseInputWidget" in str(_s) for _s in _spreads):
        _props = _schema.setdefault("properties", {})
        for _name, _cfg in BASE_INPUT_WIDGET_PROPERTIES.items():
            _props.setdefault(_name, dict(_cfg))

# The label property differs by widget: most use `label`, the select/slider/group family uses
# `labelText`. Map each type to its real label prop so update_widgets can accept either name and
# normalize (feedback item 5).
LABEL_PROP_BY_TYPE = {}
for _t, _schema in WIDGET_PROPS.items():
    _keys = (_schema.get("properties") or {}).keys()
    if "label" in _keys:
        LABEL_PROP_BY_TYPE[_t] = "label"
    elif "labelText" in _keys:
        LABEL_PROP_BY_TYPE[_t] = "labelText"

# Bake the label map into the shared update snippet once (both update_widgets and
# update_custom_widget reuse this constant).
UPDATE_WIDGETS_JS = UPDATE_WIDGETS_JS.replace("/*__LABEL_MAP__*/{}", json.dumps(LABEL_PROP_BY_TYPE))

# Controls that have a visual (non-code) UI in the property pane and a "JS" toggle. A binding on
# one of these is only visible to a maintainer when the path is in dynamicPropertyPathList.
# Event handlers (ACTION_SELECTOR) are left to the editor's own action-selector logic.
CODE_ONLY_CONTROLS = {"ACTION_SELECTOR", "INPUT_TEXT", "CODE_EDITOR"}


def _ui_controls():
    base = {
        name: cfg.get("controlType")
        for name, cfg in ((WIDGET_PROPS.get("BASE_INPUT_WIDGET") or {}).get("properties") or {}).items()
        if cfg.get("isJSConvertible") and cfg.get("controlType") not in CODE_ONLY_CONTROLS
    }
    out = {}
    for wtype, schema in WIDGET_PROPS.items():
        props = {}
        spreads = ((schema.get("defaults") or {}).get("__spreads__")) or []
        if any("BaseInputWidget" in str(s) for s in spreads):
            props.update(base)
        for name, cfg in (schema.get("properties") or {}).items():
            if cfg.get("isJSConvertible") and cfg.get("controlType") not in CODE_ONLY_CONTROLS:
                props[name] = cfg.get("controlType")
        if props:
            out[wtype] = props
    return out


UI_CONTROLS_BY_TYPE = _ui_controls()
# Sample selection each select-like widget is born with (Appsmith's blueprint "GREEN"...).
SAMPLE_DEFAULT_OPTIONS = {
    t: (s.get("defaults") or {}).get("defaultOptionValue")
    for t, s in WIDGET_PROPS.items()
    if "sourceData" in (s.get("properties") or {}) and (s.get("defaults") or {}).get("defaultOptionValue") is not None
}
POLICY = (
    PROPERTY_POLICY_JS
    .replace("/*__UI_CONTROLS__*/{}", json.dumps(UI_CONTROLS_BY_TYPE))
    .replace("/*__SAMPLE_DEFAULTS__*/{}", json.dumps(SAMPLE_DEFAULT_OPTIONS))
)
LINT_DESIGN_JS = LINT_DESIGN_JS.replace("/*__UI_CONTROLS__*/{}", json.dumps(UI_CONTROLS_BY_TYPE))
# Helpers for snippets that write widget properties.
WIDGET_WRITE = {**PERSIST, "__propertyPolicy": POLICY}

# Keys that belong to the n8n `httpRequest` node, NOT the Appsmith REST plugin. Callers reach for
# them by habit; the plugin silently ignores them (feedback 3.5), so strip + warn.
HTTP_REQUEST_STRAY_KEYS = ("sendBody", "specifyBody", "jsonBody", "bodyParameters", "sendHeaders", "sendQuery")


def _normalize_query_action_config(action_config):
    """Normalize a query's actionConfiguration for the Appsmith REST plugin (feedback 3.5).

    - `json_body` (dict/list/str) → serialized `body` string + `pluginSpecifiedTemplates:[{value:True}]`
      (Appsmith's "smart JSON substitution" so `{{ }}` inside the JSON don't break quoting) + a
      `Content-Type: application/json` header + `formData.apiContentType`. This is the shape the REST
      plugin actually persists — `sendBody`/`specifyBody`/`jsonBody` (n8n httpRequest keys) do not.
    - stray httpRequest keys are dropped with a warning.
    - empty `{"key":"","value":""}` rows in headers/queryParameters are dropped (they pollute the
      action on every merge).

    Returns `(config, warnings)`.
    """
    if not isinstance(action_config, dict):
        return action_config, []
    cfg = dict(action_config)
    warnings = []
    if "json_body" in cfg:
        jb = cfg.pop("json_body")
        if isinstance(jb, (dict, list)):
            cfg["body"] = json.dumps(jb, indent=2, ensure_ascii=False)
        elif jb is not None:
            cfg["body"] = str(jb)
        cfg.setdefault("pluginSpecifiedTemplates", [{"value": True}])
        headers = cfg.get("headers") if isinstance(cfg.get("headers"), list) else []
        if not any(isinstance(h, dict) and str(h.get("key", "")).lower() == "content-type" for h in headers):
            headers = [{"key": "Content-Type", "value": "application/json"}, *headers]
        cfg["headers"] = headers
        form_data = cfg.get("formData") if isinstance(cfg.get("formData"), dict) else {}
        form_data.setdefault("apiContentType", "application/json")
        cfg["formData"] = form_data
    stray = [k for k in HTTP_REQUEST_STRAY_KEYS if k in cfg]
    if stray:
        warnings.append(
            "ignored httpRequest-style keys " + ", ".join(stray)
            + " — the Appsmith REST plugin uses `body` (string) + pluginSpecifiedTemplates; "
            + "pass json_body=<object> for a JSON body"
        )
        for k in stray:
            cfg.pop(k, None)
    for list_key in ("headers", "queryParameters"):
        rows = cfg.get(list_key)
        if isinstance(rows, list):
            cfg[list_key] = [
                h for h in rows
                if not (isinstance(h, dict) and not str(h.get("key", "")).strip() and not str(h.get("value", "")).strip())
            ]
    return cfg, warnings


def _prep_query_entry(entry: dict) -> tuple[dict, list]:
    """Fold a top-level `json_body` into action_config and normalize it (see
    `_normalize_query_action_config`). Leaves entries without body config untouched so the
    per-plugin defaults still apply. Returns `(entry, warnings)`."""
    entry = dict(entry)
    ac = entry.get("action_config")
    jb = entry.pop("json_body", None)
    has_ac = isinstance(ac, dict) and len(ac) > 0
    if jb is not None:
        ac = dict(ac or {})
        ac["json_body"] = jb
        has_ac = True
    if not has_ac:
        return entry, []
    cfg, warnings = _normalize_query_action_config(ac)
    entry["action_config"] = cfg
    return entry, warnings


WORKSPACE_FIELDS = ("id", "name")
APP_FIELDS = ("id", "name", "slug", "workspaceId", "defaultPageId", "editorUrl")
PAGE_FIELDS = ("id", "name", "isDefault", "isHidden", "slug", "isCurrent")
PLUGIN_FIELDS = ("id", "name", "packageName", "type")
DATASOURCE_FIELDS = ("id", "name", "pluginId", "workspaceId")
QUERY_FIELDS = ("id", "name", "pageId", "pluginId", "datasourceId", "httpMethod", "path", "runBehaviour")
JS_OBJECT_FIELDS = ("id", "name", "pageId", "actions")
LOG_FIELDS = (
    "severity", "category", "timestamp", "logType", "occurrenceCount",
    "sourceName", "sourceType", "propertyPath", "text", "messages", "payloadTruncated",
)
CUSTOM_WIDGET_FIELDS = (
    "widgetId", "widgetName", "type", "srcDoc", "defaultModel", "events",
    "isVisible", "leftColumn", "topRow", "rightColumn", "bottomRow", "parentId",
)


async def ensure_ready():
    global ready
    if client.ws is None or client.session_id is None:
        # New connection means a new page (e.g. Firefox relaunched): bootstrap again.
        ready = False
    try:
        await client.connect()
    except RuntimeError as e:
        # A leaked orphan session can't be ended from a fresh connection (BiDi allows only one,
        # and session.end targets THIS connection, which has none) — so retrying just hits the
        # same wall. Surface the actionable "relaunch Firefox" guidance immediately instead of
        # looping into a confusing secondary error.
        if "active BiDi session" in str(e):
            raise
        await client.reset()
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


async def _persist_layout() -> dict:
    """Persist the current page's widget tree with the shared layout PUT (`__persistLayout`)
    from Python, for flows that change the tree outside a mutation snippet."""
    raw = await client.run_snippet("__persistLayout({})", js_helpers=PERSIST)
    return raw if isinstance(raw, dict) else {"persisted": False, "error": "no result from persist"}


def _eval_error_key(e: dict) -> tuple:
    return (e.get("entity"), e.get("property"), e.get("message"))


async def _read_eval_errors() -> list[dict]:
    raw = await client.run_snippet(GET_EVAL_ERRORS_JS)
    errs = (raw or {}).get("errors") if isinstance(raw, dict) else None
    return [e for e in (errs or []) if isinstance(e, dict)]


def _truncate_bodies(entries: list, limit: int) -> None:
    """Replace any `body` whose serialized size exceeds `limit` with a head preview."""
    for entry in entries:
        if isinstance(entry, dict) and entry.get("body") is not None:
            body = entry["body"]
            s = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
            if len(s) > limit:
                entry["body"] = {"__truncated__": True, "totalBytes": len(s), "returnedBytes": limit, "preview": s[:limit]}
                entry["truncated"] = True


def _blocked_query(query_id: str, reason: str, name: str | None = None) -> dict:
    out = {"id": query_id}
    if name is not None:
        out["name"] = name
    out.update(ok=False, blocked=True, error=reason)
    return out


async def _assess_queries(query_ids: list[str]) -> tuple[list[tuple[str, dict | None]], list[str]]:
    """Apply the fail-closed read-only execution policy to page/module queries. Returns the
    per-id decision (None = allowed, dict = blocked result) and the allowed ids in order."""
    actions = await client.run_snippet(GET_QUERIES_JS, json_constants={"IDS": query_ids})
    by_id = {a.get("id"): a for a in (actions or []) if isinstance(a, dict) and a.get("id")}
    decisions: list[tuple[str, dict | None]] = []
    allowed: list[str] = []
    for query_id in query_ids:
        action = by_id.get(query_id)
        if action is None:
            decisions.append((query_id, _blocked_query(
                query_id,
                "Execução bloqueada pela política somente leitura: metadados da query não encontrados.",
            )))
            continue
        decision = assess_query_action(action)
        if not decision.allowed:
            decisions.append((query_id, _blocked_query(query_id, decision.reason, action.get("name"))))
            continue
        allowed.append(query_id)
        decisions.append((query_id, None))
    return decisions, allowed


async def _assess_instances(instances: list[str]) -> tuple[list[tuple[str, dict | None]], list[str]]:
    """Same read-only policy for package query-module instances: the instance's public query is
    read and assessed; an instance whose query can't be read is blocked."""
    rows = await _instances("queries", {"instances": instances})
    rows = rows if isinstance(rows, list) else []
    by_ref = {r.get("ref"): r for r in (rows or []) if isinstance(r, dict)}
    decisions: list[tuple[str, dict | None]] = []
    allowed: list[str] = []
    for ref in instances:
        row = by_ref.get(ref) or {}
        if not row.get("found"):
            # Unknown instance: let the run op report "not found" (nothing is executed).
            allowed.append(ref)
            decisions.append((ref, None))
            continue
        if row.get("type") != "QUERY_MODULE":
            allowed.append(ref)  # the run op refuses non-query instances itself
            decisions.append((ref, None))
            continue
        action = row.get("action")
        if not action:
            decisions.append((ref, _blocked_query(
                row.get("id") or ref,
                "Execução bloqueada pela política somente leitura: query da instância não encontrada.",
                row.get("name"),
            )))
            continue
        decision = assess_query_action(action)
        if not decision.allowed:
            decisions.append((ref, _blocked_query(row.get("id") or ref, decision.reason, row.get("name"))))
            continue
        allowed.append(ref)
        decisions.append((ref, None))
    return decisions, allowed


@mcp.tool()
async def get_capabilities() -> dict:
    """Describe registered tools, MCP version and execution restrictions without connecting
    to Firefox. Runtime/module availability is unverified; use get_build_context to inspect
    the editor. Use get_guide() to list bundled recipes, then get_guide(slug) to read one."""
    return build_capabilities([tool.name for tool in await mcp.list_tools()])


@mcp.tool()
async def get_guide(slug: str | None = None) -> dict:
    """List bundled recipe titles when slug is omitted, or read one recipe by its listed
    slug. Works offline, without Firefox. Unknown slugs return the available choices;
    filesystem paths are never accepted. Start with reading-state or diagnostics."""
    return read_guide(slug)


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
            raise RuntimeError(
                "No workspaces in the Redux store — the editor does not load the workspace "
                "list. Either pass workspace_id (list_apps reports one per app), or call "
                "navigate('<instance>/applications') first."
            )
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
    to the currently open application.

    Renaming regenerates the app's URL slug, which breaks existing `/app/<slug>/...` URLs
    (email links, Supabase Site/Redirect URLs, bookmarks). When `name` is set, the result
    reports `oldSlug`/`newSlug`/`slugChanged` and a `warning` so you can fix those URLs."""
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
async def get_logs(limit: int = 50, include_messages: bool = False) -> dict:
    """Return Appsmith's debugger logs and errors.

    By default only metadata — severity, category, timestamp, source name/type, and the
    `propertyPath` that failed. Pass `include_messages=true` to get the error text as
    well; without it there is no way to tell *why* a widget is blank. Message text on
    entries sourced from a query is capped at 300 characters so a response payload is not
    dumped wholesale, but the failure reason is preserved.

    An empty `errors` list does not mean the page is healthy — a widget can render blank
    with nothing logged. Use `get_render_health` / `get_eval_errors` for that."""
    await ensure_ready()
    raw = await client.run_snippet(
        LOG_METADATA_JS,
        json_constants={
            "SEVERITY": None,
            "LIMIT": int(limit),
            "INCLUDE_MESSAGES": bool(include_messages),
        },
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
async def add_widgets(widgets: list[dict], allow_bindings: list[str] | None = None) -> list:
    """Add multiple widgets in one tool call. Each entry is the same shape as `add_widget`'s
    args: `{widget_type, parent_id?, left?, top?, columns?, rows?, props?, name?, new_id?}`.
    `columns` and `rows` default to each widget type's own getDefaults() values.

    `parent_id` may be a wrapper widget (MODAL/CONTAINER/TABS/FORM/LIST/STATBOX) — it is
    auto-redirected to that widget's inner CANVAS_WIDGET so the child actually renders (passing a
    modal/container id used to parent the child on the invisible wrapper, producing an empty
    card/modal with no error). When redirected, the result reports `effectiveParentId` and
    `redirectedToInnerCanvas`. For a TABS_WIDGET this targets the first tab's canvas — pass a
    specific tab's canvas id to target another tab.

    `props` follow the same property policy as update_widgets (bindings, triggers, JS toggle,
    `{{query.data}}` normalization, sample select default cleared) and REPLACE the blueprint
    defaults instead of merging into them (so a chart's sample series never survives).

    Geometry goes in `left`/`top`/`columns`/`rows`, never in `props` — layout properties passed
    through `props` are refused.

    A binding on a property whose pane control is visual (switch, dropdown, colour, Data
    selector) is also refused, because that control cannot display code and the field would
    look empty to whoever maintains the page. Authorise a genuinely needed condition by the
    name you are giving the widget: `allow_bindings=["sel_novo.isVisible"]`.

    Returns a list of `{widgetId, widgetName, type, parent, box, applied?}` per widget, in the same
    order, plus `overlaps` (siblings the new widget landed on top of) and `notes` for defaults that
    silently change behaviour (e.g. a DATE_PICKER_WIDGET2 starts at today, not empty, which quietly
    filters out every row). A MODAL_WIDGET's skeleton close/cancel buttons are rewired to the
    modal's real name."""
    await ensure_ready()
    widgets = widgets or []
    problems, warnings = validate_new_widget_props(widgets, WIDGET_PROPS)
    if problems:
        raise ValueError(format_problems(problems, "add_widgets"))
    # The widget has no name yet, so authorisation uses the name being given to it.
    panel_problems, _ = validate_panel_writes(
        [
            {
                "label": spec.get("name") or spec.get("new_id") or f"widgets[{i}]",
                "type": spec.get("widget_type") or "",
                "props": spec.get("props") or {},
            }
            for i, spec in enumerate(widgets)
        ],
        UI_CONTROLS_BY_TYPE,
        allow_bindings=allow_bindings,
    )
    if panel_problems:
        raise ValueError(format_problems(panel_problems, "add_widgets"))
    resolved = []
    for spec in widgets:
        wt = spec.get("widget_type")
        defaults = WIDGET_PROPS.get(wt, {}).get("defaults", {})
        # Normalize label/labelText to whichever this widget type actually renders (INPUT_WIDGET_V2
        # renders `label`, the select/slider family renders `labelText`) so a caller passing the
        # wrong name doesn't leave the widget showing the default "Label" (feedback 3.5).
        props = dict(spec.get("props") or {})
        label_prop = LABEL_PROP_BY_TYPE.get(wt)
        if label_prop:
            other = "labelText" if label_prop == "label" else "label"
            if other in props and label_prop not in props:
                props[label_prop] = props.pop(other)
        resolved.append({
            "widget_type": wt,
            "parent_id": spec.get("parent_id", "0"),
            "left": int(spec.get("left", 1)),
            "top": int(spec.get("top", 1)),
            "columns": int(spec.get("columns") if spec.get("columns") is not None else (defaults.get("columns") or 16)),
            "rows": int(spec.get("rows") if spec.get("rows") is not None else (defaults.get("rows") or 4)),
            "props": props,
            "name": spec.get("name"),
            "new_id": spec.get("new_id"),
        })
    raw = await client.run_snippet(
        ADD_WIDGETS_JS,
        json_constants={"WIDGETS": resolved},
        js_helpers=WIDGET_WRITE,
    )
    results = raw if isinstance(raw, list) else []
    for entry, spec in zip(results, widgets):
        if not isinstance(entry, dict):
            continue
        notes = side_effect_notes(spec.get("widget_type"), spec.get("props"))
        notes += [w["warning"] for w in warnings if w["widget"] == (spec.get("name") or "")]
        if entry.get("overlaps"):
            notes.append(
                "lands on top of existing widget(s): "
                + ", ".join(str(o) for o in entry["overlaps"])
                + " — reposition with set_widget_bounds"
            )
        if notes:
            entry["notes"] = notes
    return results


@mcp.tool()
async def update_widgets(
    updates: list[dict],
    force: bool = False,
    allow_unknown_props: bool = False,
    check_eval: bool = False,
    allow_bindings: list[str] | None = None,
) -> list:
    """Apply **configuration** property updates to one or more widgets. Each entry is
    `{"widget_id": <id>, "props": {<prop>: <value>, ...}}`.

    Geometry, structure and composite properties are owned by other tools and are refused here,
    because writing them produces a state the editor cannot create (a blank widget or an
    unloadable page on the *next* load, with nothing in the debugger):
      - position/size/height mode → `set_widget_bounds`
      - `primaryColumns`/`columnOrder` → `manage_table_columns` (dotted
        `primaryColumns.<col>.<prop>` string values are accepted and validated against the
        column sub-schema)
      - `tabsObj` → `manage_tabs`
      - `widgetName` → `rename_widgets`
      - `parentId` → `reparent_widgets`
    Escape hatches: `allow_unknown_props=true` downgrades "not in the schema" to warnings (the
    dumped schema lags the running Appsmith) but still refuses owned properties; `force=true`
    overrides everything and can corrupt the page. A `label`/`labelText` mix-up is normalized to
    the property the widget actually has (reported in `warnings`). `check_eval=true` re-reads the
    evaluation errors after the write and reports the newly introduced ones as `newEvalErrors`.

    Dict values are deep-merged with existing state — so to change just one sub-key you
    can pass `{"srcDoc": {"css": "..."}}` without resending html/js. Non-dict values are
    replaced.

    Properties are stored the way the property pane stores them:
      - properties whose name starts with `on` (e.g. `onClick`) are registered as triggers.
      - string values containing `{{...}}` are registered as dynamic bindings.
      - any other value is a literal and is removed from the dynamic path lists.
      - a binding on a property with a visual control (switch, dropdown, colour, Data selector)
        turns its "JS" toggle on (dynamicPropertyPathList) so the code is visible in the pane;
        a literal turns it off. Theme bindings (`{{appsmith.theme...}}`) keep the visual control.
      - table `tableData` / select `sourceData` given as `{{ query.data }}` is normalized to
        `{{query.data}}` so the Data dropdown shows the query — for connecting data prefer
        `connect_widget_data`, and keep transformations in the query instead of the binding.
      - supplying select `sourceData` without `defaultOptionValue` clears the sample "GREEN".

    Every property must stay readable in the pane, so a binding on a property whose pane
    control is visual (switch, dropdown, colour, Data selector) is REFUSED: that control
    cannot display code, and the field would look empty to whoever maintains the page. Write a
    literal value; for data use `connect_widget_data` and keep transformations in the query.
    When a condition genuinely needs code, check the Appsmith docs for a native way first, then
    authorise the exact path with `allow_bindings=["Widget1.isVisible"]` — it is written with
    the pane's "JS" toggle on, so the code is visible and editable there. `{{query.data}}`,
    `{{appsmith.theme...}}` and a table column's `currentRow` props are native and never need
    authorising. Authorised paths come back as `panel.authorizedBindings`.

    Composite widgets (Statbox) and Modal show/hide are delegated automatically.
    Returns a list of per-widget results, each with any `warnings` raised for it."""
    await ensure_ready()
    updates = updates or []
    described = await client.run_snippet(
        DESCRIBE_WIDGETS_JS,
        json_constants={"IDS": [u.get("widget_id") for u in updates]},
    )
    described = described if isinstance(described, list) else []
    by_id = {d.get("widgetId"): d for d in described if isinstance(d, dict)}

    # Normalize label/labelText before validating, so the right name isn't refused.
    remap_notes: dict[str, list[str]] = {}
    for u in updates:
        info = by_id.get(u.get("widget_id"))
        props = u.get("props") or {}
        if not info or info.get("missing") or not props:
            continue
        known, _ = _known_props(info.get("type") or "", info.get("keys"), WIDGET_PROPS)
        remaps = resolve_label_synonyms(props, known)
        if remaps:
            u["props"] = {remaps.get(k, k): v for k, v in props.items()}
            for wrong, right in remaps.items():
                remap_notes.setdefault(u.get("widget_id"), []).append(
                    f"normalized '{wrong}' -> '{right}' (this widget's label property)"
                )

    problems, warnings = validate_widget_updates(
        updates, described, WIDGET_PROPS,
        allow_unknown=force or allow_unknown_props,
    )
    if problems and not force:
        raise ValueError(format_problems(problems, "update_widgets"))

    # Refuse writes the property pane could not show, so no configuration becomes invisible.
    panel_problems, authorized = validate_panel_writes(
        [
            {
                "label": (by_id.get(u.get("widget_id")) or {}).get("name") or u.get("widget_id"),
                "type": (by_id.get(u.get("widget_id")) or {}).get("type") or "",
                "props": u.get("props") or {},
            }
            for u in updates
            if (by_id.get(u.get("widget_id")) or {}).get("type")
        ],
        UI_CONTROLS_BY_TYPE,
        allow_bindings=allow_bindings,
    )
    if panel_problems and not force:
        raise ValueError(format_problems(panel_problems, "update_widgets"))

    before = {_eval_error_key(e) for e in await _read_eval_errors()} if check_eval else set()

    raw = await client.run_snippet(
        UPDATE_WIDGETS_JS,
        json_constants={"UPDATES": updates},
        js_helpers=WIDGET_WRITE,
    )
    results = raw if isinstance(raw, list) else []
    for entry in results:
        if isinstance(entry, dict):
            notes = [w["warning"] for w in warnings if w["widgetId"] == entry.get("widgetId")]
            notes += remap_notes.get(entry.get("widgetId"), [])
            if notes:
                entry.setdefault("warnings", []).extend(notes)

    if authorized and results and isinstance(results[0], dict):
        results[0].setdefault("panel", {})["authorizedBindings"] = authorized

    if check_eval:
        new_errs = [e for e in await _read_eval_errors() if _eval_error_key(e) not in before]
        if new_errs:
            by_name = {e.get("name") or e.get("widgetName"): e for e in results if isinstance(e, dict)}
            unmatched = []
            for err in new_errs:
                target = by_name.get(err.get("entity"))
                if target is not None:
                    target.setdefault("newEvalErrors", []).append(err)
                else:
                    unmatched.append(err)
            # Errors under an entity we didn't touch still matter — surface them once.
            if unmatched and results and isinstance(results[0], dict):
                results[0].setdefault("newEvalErrors", []).extend(unmatched)
    return results


# Friendly option name -> the TABLE_WIDGET_V2 property the pane writes.
_TABLE_OPTIONS = {
    "server_side_pagination": "serverSidePaginationEnabled",
    "total_record_count": "totalRecordsCount",
    "search": "isVisibleSearch",
    "client_side_search": "enableClientSideSearch",
    "default_search_text": "defaultSearchText",
    "filters": "isVisibleFilters",
    "download": "isVisibleDownload",
    "pagination": "isVisiblePagination",
    "multi_row_selection": "multiRowSelection",
    "default_selected_row": "defaultSelectedRow",
    "inline_save": "inlineEditingSaveOption",
    "allow_add_new_row": "allowAddNewRow",
}

_VALIDATION_RULES = {
    "required": "isRequired",
    "regex": "regex",
    "error_message": "errorMessage",
    "max_chars": "maxChars",
    "min": "minNum",
    "max": "maxNum",
    "min_date": "minDate",
    "max_date": "maxDate",
}


@mcp.tool()
async def configure_table(
    widget_id: str,
    server_side_pagination: bool | None = None,
    total_record_count: int | None = None,
    search: bool | None = None,
    client_side_search: bool | None = None,
    default_search_text: str | None = None,
    filters: bool | None = None,
    download: bool | None = None,
    pagination: bool | None = None,
    multi_row_selection: bool | None = None,
    default_selected_row: int | str | None = None,
    inline_save: Literal["ROW_LEVEL", "CUSTOM"] | None = None,
    allow_add_new_row: bool | None = None,
) -> dict:
    """Configure a TABLE_WIDGET_V2 through the property pane's own controls.

    Options, all literal and all visible in the pane: `server_side_pagination`,
    `total_record_count`, `search`, `client_side_search`, `default_search_text`, `filters`,
    `download`, `pagination`, `multi_row_selection`, `default_selected_row`,
    `inline_save` ("ROW_LEVEL"|"CUSTOM"), `allow_add_new_row`.

    Also reports combinations Appsmith stores but never runs: server-side pagination with no
    `onPageChange`, server-side search (`client_side_search=false`) with no
    `onSearchTextChanged`, and add-new-row with no editable column — each shows up only as
    "the table doesn't work", far from the call that caused it.

    Omitted/None options are unchanged; false, zero and empty strings are written.
    Returns `{ok, persisted, applied, warnings}`; an unconfirmed save raises an error.
    Columns are `manage_table_columns`, data is
    `connect_widget_data`, handlers are `set_widget_events`."""
    values = locals()
    options = {key: values[key] for key in _TABLE_OPTIONS if values[key] is not None}
    if not options:
        return {"ok": True, "persisted": False, "noOp": True, "applied": {}, "warnings": []}
    await ensure_ready()
    described = await client.run_snippet(DESCRIBE_WIDGETS_JS, json_constants={"IDS": [widget_id]})
    info = described[0] if isinstance(described, list) and described else {}
    if info.get("type") != "TABLE_WIDGET_V2":
        raise ValueError(
            f"configure_table: {widget_id} is a {info.get('type') or 'missing widget'}, "
            f"not a TABLE_WIDGET_V2"
        )

    handlers = set(info.get("handlers") or [])
    warnings = []
    if options.get("server_side_pagination") and "onPageChange" not in handlers:
        warnings.append(
            "server_side_pagination is on but the table has no onPageChange — it will never "
            "fetch the next page; wire it with set_widget_events"
        )
    if options.get("client_side_search") is False and "onSearchTextChanged" not in handlers:
        warnings.append(
            "client_side_search is off (server-side search) but there is no "
            "onSearchTextChanged — the search box will not filter anything"
        )
    if options.get("allow_add_new_row") and not (info.get("editableColumns") or []):
        warnings.append(
            "allow_add_new_row is on but no column is editable — the new row cannot be "
            "filled; set editable=true on a column with manage_table_columns"
        )

    props = {_TABLE_OPTIONS[k]: v for k, v in options.items()}
    updates = [{"widget_id": widget_id, "props": props}]
    outcome = _persistence_outcomes(updates, await update_widgets(updates))[0]
    _raise_if_all_failed("configure_table", [outcome])
    return {"ok": True, "persisted": True, "applied": props,
            "warnings": warnings + outcome.get("warnings", [])}


@mcp.tool()
async def set_validation(
    widget_id: str,
    required: bool | None = None,
    regex: str | None = None,
    error_message: str | None = None,
    max_chars: int | None = None,
    min: int | float | None = None,
    max: int | float | None = None,
    min_date: str | None = None,
    max_date: str | None = None,
) -> dict:
    """Set an input widget's validation through the pane's Validation section.

    Rules: `required`, `regex`, `error_message`, `max_chars`, `min`, `max`, `min_date`,
    `max_date`. All literal, all visible in the pane. `error_message` is what the user sees
    when `regex` fails, so set the two together. Omitted/None rules are unchanged.
    Returns `{ok, persisted, applied, warnings}`; an unconfirmed save raises an error."""
    values = locals()
    rules = {key: values[key] for key in _VALIDATION_RULES if values[key] is not None}
    if not rules:
        return {"ok": True, "persisted": False, "noOp": True, "applied": {}, "warnings": []}
    await ensure_ready()
    props = {_VALIDATION_RULES[k]: v for k, v in rules.items()}
    updates = [{"widget_id": widget_id, "props": props}]
    outcome = _persistence_outcomes(updates, await update_widgets(updates))[0]
    _raise_if_all_failed("set_validation", [outcome])
    return {"ok": True, "persisted": True, "applied": props,
            "warnings": outcome.get("warnings", [])}


def _persistence_outcomes(updates: list[dict], results) -> list[dict]:
    """Keep ordered per-target results; missing or mismatched save evidence fails closed."""
    outcomes = []
    for index, update in enumerate(updates):
        target = update["widget_id"]
        result = results[index] if isinstance(results, list) and index < len(results) else None
        outcome = {"widget": target, "ok": False, "persisted": False}
        if not isinstance(result, dict) or result.get("widgetId") != target:
            outcome["error"] = f"save not confirmed for {target}: missing or mismatched result"
        elif result.get("error"):
            outcome["error"] = str(result["error"])
        elif result.get("persisted") is not True:
            outcome["error"] = f"save not confirmed for {target}"
        else:
            outcome.update(ok=True, persisted=True)
        if isinstance(result, dict) and isinstance(result.get("warnings"), list):
            outcome["warnings"] = result["warnings"]
        outcomes.append(outcome)
    return outcomes


def _raise_if_all_failed(tool_name: str, outcomes: list[dict]) -> None:
    if outcomes and not any(outcome["ok"] for outcome in outcomes):
        detail = "; ".join(f"{outcome['widget']}: {outcome['error']}" for outcome in outcomes)
        raise ValueError(f"{tool_name}: {detail}")


@mcp.tool()
async def set_widget_events(events: list[dict]) -> list:
    """Wire widget events the way the property pane's action selector does.

    Each entry `{"widget": <name|id>, "events": {"onClick": {"action": "run_query",
    "query": "q_salvar"}}}`. Supported actions: `run_query` (query), `run_js` (object,
    function), `show_alert` (message, style?), `show_modal`/`close_modal` (modal),
    `navigate_to` (page|url, params?, target?), `store_value` (key, value), `clear_store`,
    `download` (data, name), `copy_to_clipboard` (text), `reset_widget` (widget),
    `set_interval` (callback, ms?, id?), `clear_interval` (id), `post_message` (message).

    Add `on_success`/`on_failure` to chain, or pass `{"code": "{{ ... }}"}` for anything the
    list does not cover. Both are written, but the pane then shows raw code instead of the
    dropdown — the result says which, per event, in `native`.

    Returns `[{widget, event, code, native, ok, persisted, error?}]`, preserving partial
    failures per event. Repeated widget/event pairs are coalesced before saving: the last
    code wins and only that final value is reported. If every target failed, raises an error.
    For a table column's handler use
    `manage_table_columns`, which knows which event each column type fires."""
    by_widget, by_event = {}, {}
    for entry in events or []:
        target = entry.get("widget")
        if not isinstance(target, str) or not target:
            raise ValueError("set_widget_events: widget must be a non-empty id or name")
        for event, spec in (entry.get("events") or {}).items():
            code, native = build_action(spec if isinstance(spec, dict) else {"code": spec})
            by_widget.setdefault(target, {"widget_id": target, "props": {}})["props"][event] = code
            by_event[target, event] = {"widget": target, "event": event, "code": code, "native": native}
    updates, report = list(by_widget.values()), list(by_event.values())
    if updates:
        await ensure_ready()
        outcomes = _persistence_outcomes(updates, await update_widgets(updates))
        by_target = {outcome["widget"]: outcome for outcome in outcomes}
        for event_result in report:
            event_result.update(by_target[event_result["widget"]])
        _raise_if_all_failed("set_widget_events", outcomes)
    return report


@mcp.tool()
async def delete_widgets(widget_ids: list[str]) -> list:
    """Delete multiple widgets in one tool call. Cascades children, disallowUndo is set."""
    await ensure_ready()
    raw = await client.run_snippet(
        DELETE_WIDGETS_JS,
        json_constants={"WIDGET_IDS": widget_ids or []},
        js_helpers=PERSIST,
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def set_widget_bounds(updates: list[dict]) -> list:
    """Move and/or resize multiple widgets in one tool call. Each entry is
    `{"widget_id": <id>, "left": <int>, "top": <int>, "columns": <int>,
    "rows": <int>}` — `left`/`top` set the top-left, `columns`/`rows` set the
    size; any omitted field is preserved per widget. When `rows` is given,
    auto-height widgets are switched to FIXED so the resize sticks (reported as
    `heightModeOverridden`).

    Returns the *effective* box after the layout engine's collision/reflow pass — not an echo of
    the request. When a sibling pushed the widget off the requested position, `moved` is true and
    `requested` carries what you asked for. Persisted with the layout PUT (`persisted: true`)."""
    await ensure_ready()
    raw = await client.run_snippet(
        SET_WIDGET_BOUNDS_JS,
        json_constants={"UPDATES": updates or []},
        js_helpers=PERSIST,
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
        js_helpers=PERSIST,
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
    "new_parent_id": <id>}`. If `new_parent_id` is a container/tabs/form (not itself a
    CANVAS_WIDGET), it is auto-redirected to that widget's inner CANVAS_WIDGET (for TABS,
    the first tab's canvas — pass a specific tab's canvas id to target another tab);
    the result reports `redirectedToInnerCanvas`. Position is preserved verbatim — call
    set_widget_bounds afterwards if the new parent's snap dimensions differ."""
    await ensure_ready()
    raw = await client.run_snippet(
        REPARENT_WIDGETS_JS,
        json_constants={"UPDATES": updates or []},
        js_helpers=PERSIST,
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def clear_canvas() -> dict:
    """Delete every widget directly under MainContainer. Cascades to nested children."""
    await ensure_ready()
    raw = await client.run_snippet(CLEAR_CANVAS_JS, js_helpers=PERSIST)
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def get_widget(widget_id: str, include_source: bool = False, fields: list[str] | None = None) -> dict:
    """Return the Redux record for a widget — every property currently set, including
    position, type-specific config, and dynamic binding paths. `widget_id` accepts a hex id OR
    a widget name.

    For CUSTOM_WIDGET the `srcDoc`/`uncompiledSrcDoc` source (tens of KB, duplicated) is
    stripped by default and replaced with a `sourceOmitted` byte summary — pass
    `include_source=True` to keep it, or use `get_custom_widget` for the source. Pass
    `fields=[...]` to project down to just those keys (e.g.
    `["dynamicTriggerPathList", "dynamicHeight", "topRow", "leftColumn"]`)."""
    await ensure_ready()
    raw = await client.run_snippet(
        GET_WIDGET_JS,
        json_constants={
            "WIDGET_ID": widget_id,
            "INCLUDE_SOURCE": bool(include_source),
            "FIELDS": fields or [],
        },
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def list_widgets() -> list:
    """Return a light flat map of every widget on the current page — `{id, name, type,
    parentId, leftColumn, topRow, rightColumn, bottomRow, isVisible}` each, sorted top-left
    to bottom-right. The cheap "where is everything / what is this widget called" read;
    `find_widgets` filters by type/props/parent, `export_page` is the whole DSL."""
    await ensure_ready()
    raw = await client.run_snippet(LIST_WIDGETS_JS)
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def list_children(parent_id: str) -> list | dict:
    """List only the direct children of a widget or canvas, by id or widget name.

    Returns lightweight id/name/type/position metadata, including Appsmith's default modal
    children. This is a fixed read-only store inspection; it never evaluates caller-provided
    JavaScript."""
    await ensure_ready()
    raw = await client.run_snippet(
        INSPECT_STATE_JS,
        json_constants={"MODE": "list_children", "ARG": {"parent_id": parent_id}},
    )
    return raw if isinstance(raw, (list, dict)) else {"raw": raw}


@mcp.tool()
async def check_layout() -> dict:
    """Diagnose layout/render issues across the current page. First waits (bounded) for
    in-flight queries to settle so loading skeletons aren't mistaken for defects. Returns:

    - `settled` / `pendingQueries`: whether queries were still loading when measured (if
      `settled` is false, re-run before trusting `problems`).
    - `problems`: the widgets that actually look wrong — grid overlaps, content overflow, or
      missing from the DOM for no legitimate reason.
    - `widgets`: every widget with `status` (`ok` | `expected` | `problem`), grid box,
      `overlaps`, rendered pixel box, overflow, and iframe inner scrollHeight (Custom/Iframe).
      A widget missing from the DOM because it's inside a closed modal, an inactive tab, or a
      hidden container is `expected` with an `expectedReason` — not a problem.
    - `layoutByParent`: per container, `rows` (which widgets share a top) and `gaps` (empty
      vertical bands ≥4 rows) — use to catch a widget pushed off its intended row or an
      unintended gap between blocks, which `set_widget_bounds` can't reveal (it echoes the
      requested top, not the effective one).

    Then call set_widget_bounds / update_widgets to fix what's under `problems`."""
    await ensure_ready()
    raw = await client.run_snippet(CHECK_LAYOUT_JS)
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def lint_design() -> dict:
    """Design lint for the current page — answers "does it look good?" the way check_layout
    answers "is it broken?". Read-only. Flags exactly the things a human reviewer sends back,
    each detectable by rule:

    - `input_without_label`: a labelled input/select with an empty label.
    - `interactive_without_tooltip`: an interactive widget with no tooltip hint.
    - `button_without_icon`: a button with no `iconName`.
    - `hardcoded_color`: a style color set to a raw hex where a theme token exists.
    - `table_raw_column_label`: a visible table column still showing its raw query column name.
    - `table_bad_fallback`: a column `computedValue` whose empty-table fallback is a bare
      identifier (throws `ReferenceError` when empty) instead of `[]`.
    - `modal_binds_query_data`: a widget inside a modal bound to `<query>.data` — make sure the
      open handler re-runs the query before `showModal` (no need to copy data into the store).
    - `binding_hidden_in_ui`: a `{{ }}` on a property whose pane shows a visual control (switch,
      dropdown, colour, Data selector) without JS mode — the maintainer can't see the code.
    - `data_transformed_in_binding`: table/select data shaped inline instead of in the query.
    - `default_widget_name`: widget still named Button1/Table2/... .
    - `automatic_run_behaviour`: a query or JS function left on AUTOMATIC (see set_run_behaviour).
    - `table_visible_id_column`: an id-like table column left visible.
    - `row_misaligned`: side-by-side widgets meant to share a row that start on different rows.
    - `vertical_gap`: an empty band of ≥6 rows above a block in its container.

    Returns `{count, warnCount, findings:[{rule, severity, widget, id, type, detail, ...}]}`."""
    await ensure_ready()
    raw = await client.run_snippet(LINT_DESIGN_JS)
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def reset_widget_tree(container_id: str) -> dict:
    """Generate the `resetWidget(...)` calls for every stateful descendant of a container/modal,
    so a close/cancel/search handler can clear the whole subtree without hand-listing widgets
    (and silently forgetting one). Read-only — it returns code, it doesn't run it. Paste the
    returned `js` into the handler. `container_id` accepts a hex id or a widget name; for a modal
    the `js` also ends with its `closeModal(...)`.
    Returns `{container, containerType, isModal, widgets:[names], count, js}`."""
    await ensure_ready()
    raw = await client.run_snippet(
        RESET_WIDGET_TREE_JS,
        json_constants={"CONTAINER_ID": container_id},
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def create_pages(names: list[str]) -> list:
    """Create multiple blank pages in the current application in one tool call. Waits for
    each create to land and returns its real `pageId` (or null if it didn't appear in time),
    so you can immediately switch_page / target it."""
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
    """Switch the editor to a different page — and actually load it. Dispatching the page
    change alone only flips the *selected* page id while the canvas keeps rendering the old
    page, so widget mutations would land on (and corrupt) the wrong page. This fetches and
    renders the target, then waits until the selected and rendered page ids both settle on it.
    It also updates the browser URL to the target page, so a later refresh_page reloads THIS
    page instead of the one the URL still pointed at. Returns `{pageId, switched,
    selectedPageId, renderedPageId, consistent, urlUpdated, url}` (or `error` if it didn't finish
    loading). Prefer this over `navigate` for changing pages mid-build."""
    await ensure_ready()
    raw = await client.run_snippet(
        SWITCH_PAGE_JS,
        json_constants={"PAGE_ID": page_id},
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def get_build_context() -> dict:
    """Report where widget mutations will land, so you can catch a page mismatch before
    writing. Returns `{selectedPageId, renderedPageId, selectedPageName, renderedPageName,
    url, urlPageId, consistent, rootChildren, applicationId}` (`context: "page"`), or the module
    fields when a package module is open (`context: "module"`). `consistent` is false when the canvas is
    still rendering a different page than the one selected — call switch_page before mutating,
    or the persist layer will refuse the write to avoid corrupting the other page."""
    await ensure_ready()
    raw = await client.run_snippet(GET_BUILD_CONTEXT_JS)
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def get_eval_errors() -> dict:
    """Return the editor's current evaluation errors — the red binding/query/JS errors on the
    eval dataTree — so you can close the debug loop after wiring bindings. Each entry is
    `{entity, entityType, id, property, message, errorType, binding}` (e.g. a widget property
    whose `{{...}}` references something undefined, a broken query, or a JS parse error).
    Returns `{count, errors}`; an empty list means nothing is currently erroring."""
    await ensure_ready()
    raw = await client.run_snippet(GET_EVAL_ERRORS_JS)
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def find_widgets(where: dict | None = None, widget_type: str | None = None, parent_id: str | None = None) -> dict:
    """Grep the current page's widgets by type, property value, and/or parent — instead of
    hand-writing a canvasWidgets scan in run_command. `widget_type` filters by type (e.g.
    "TABLE_WIDGET_V2"). `where` matches top-level props: a value of `"*"` means "set to a
    non-empty value", anything else is an exact match (e.g. `{"label": "Label"}` finds every input
    still showing the default label). `parent_id` lists just the children of a container/tabs/
    form/modal (pass the container id — it resolves to the inner canvas automatically), e.g. to
    find a fresh modal's default skeleton widgets to delete. Returns
    `{count, widgets:[{id, name, type, matched?}]}`. With no args, lists every widget on the
    page."""
    await ensure_ready()
    raw = await client.run_snippet(
        FIND_WIDGETS_JS,
        json_constants={"WHERE": where or {}, "TYPE": widget_type, "PARENT_ID": parent_id},
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def get_widget_style(widget_id: str) -> dict:
    """Return a widget's resolved style block — color/border/shadow/radius/typography props in one
    read, instead of pulling them one at a time via run_command. Returns
    `{id, name, type, style:{...}}` (only style props actually set on the widget)."""
    await ensure_ready()
    raw = await client.run_snippet(GET_WIDGET_STYLE_JS, json_constants={"WIDGET_ID": widget_id})
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def get_page_background() -> dict:
    """Return the page/artboard background color. `MainContainer.backgroundColor` is often
    "none"/unset (the app then shows the theme background), so this also returns the theme
    background and the `effective` color to use when matching a widget to the page background.
    Returns `{mainContainerBackground, themeBackground, effective}`."""
    await ensure_ready()
    raw = await client.run_snippet(GET_PAGE_BACKGROUND_JS)
    return raw if isinstance(raw, dict) else {"raw": raw}


async def _eval_one(path: str) -> dict:
    raw = await client.run_snippet(
        INSPECT_STATE_JS,
        json_constants={"MODE": "eval_value", "ARG": {"path": path}},
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def eval_value(paths: list[str] | str) -> dict:
    """Read the EVALUATED (runtime) value of any binding/property off the eval dataTree — what
    Appsmith actually computed, which the write tools' `applied` summary can't confirm. Each path
    is `"<entityName>.<dotted.path>"` and may include array indices, e.g.
    `["tb_itens.primaryColumns.id_local.selectOptions", "q_users.data[0].name",
    "securityJS.currentUser"]`. Pair with get_eval_errors to close the binding-debug loop.

    Only property names and numeric indexes are accepted — nothing is evaluated as code — and
    token/password/secret-like values are replaced with `[REDACTED]` inside the browser.
    With a list, returns a map of path -> value (null if it doesn't resolve). With a single path
    string, returns `{path, found, value}`."""
    await ensure_ready()
    if isinstance(paths, str):
        return await _eval_one(paths)
    out = {}
    for p in paths or []:
        r = await _eval_one(p)
        out[p] = r.get("value") if r.get("found") else None
    return out


@mcp.tool()
async def get_store(keys: list[str] | None = None) -> dict:
    """Return the current `appsmith.store` (the in-memory key/value store that `storeValue` writes
    and `{{appsmith.store.*}}` reads), optionally limited to `keys`. Token/password/secret-like
    keys are replaced with `[REDACTED]` before leaving the browser. Returns `{store:{...}}`."""
    await ensure_ready()
    raw = await client.run_snippet(
        INSPECT_STATE_JS,
        json_constants={"MODE": "get_store", "ARG": {"keys": keys or []}},
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def set_store(entries: list[dict]) -> dict:
    """Write `appsmith.store` values the real way — so you can test a stateful/session-gated app
    without hacking localStorage + reload. Each entry is `{"key", "value", "persist"?}`. The value
    lands in Redux and the eval tree immediately (bindings re-evaluate), mirroring
    `storeValue(key, value, persist)`. `persist: true` also writes the app's persistent store so it
    survives a reload. (JS-object code runs in a worker that can't reach the page, which is why
    storeValue can't be driven directly — this dispatches the same update from the main thread.)
    Returns `{applied:[{key, persist}], store}`."""
    await ensure_ready()
    raw = await client.run_snippet(SET_STORE_JS, json_constants={"ENTRIES": entries or []})
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
async def get_datasource(datasource_id: str) -> dict:
    """Return a datasource's effective per-environment configuration with secrets masked.

    `datasource_id` accepts an id or name. Passwords, tokens, secrets, API keys, private
    keys, and sensitive header values are replaced with `[REDACTED]` inside the browser
    before the result crosses the MCP boundary."""
    await ensure_ready()
    raw = await client.run_snippet(
        INSPECT_STATE_JS,
        json_constants={
            "MODE": "get_datasource",
            "ARG": {"datasource_id": datasource_id},
        },
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def list_queries() -> list:
    """List queries (a.k.a. actions) for the currently open application."""
    await ensure_ready()
    raw = await client.run_snippet(LIST_QUERIES_JS)
    return [pick(q, QUERY_FIELDS) for q in (raw or []) if isinstance(q, dict)]


@mcp.tool()
async def get_queries(query_ids: list[str] | None = None) -> list:
    """Return the full configuration of queries — each query's `actionConfiguration`
    (httpMethod, path, headers, body, pluginSpecifiedTemplates, formData, ...) plus
    id/name/pageId/pluginId/datasourceId/runBehaviour. Pass a list of ids to filter;
    omit it (or pass an empty list) to return them all. Symmetric to get_js_objects —
    use it to read an existing query's config so you can replicate or edit it. Literal values
    in Authorization/API-key headers are replaced with `[REDACTED]`; binding expressions are
    preserved."""
    await ensure_ready()
    raw = await client.run_snippet(
        GET_QUERIES_JS,
        json_constants={"IDS": query_ids or []},
    )
    return raw if isinstance(raw, list) else []


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
    API. Each entry is `{"name", "datasource_id", "action_config"?, "page_id"?,
    "dynamic_binding_paths"?}`. If `action_config` is omitted, a per-plugin default is used:
    REST → GET / with empty headers/params; SQL DBs → `SELECT 1;`; Mongo → FIND with `{}`
    and limit 10. `page_id` defaults to the currently open page.

    For a REST POST/PUT with a JSON body, pass `json_body` (an object) — either as a top-level
    entry key or inside `action_config` — and it's serialized into the plugin's `body` string with
    smart `{{ }}` substitution enabled and a `Content-Type: application/json` header added (the
    plugin ignores the n8n-style `sendBody`/`specifyBody`/`jsonBody` keys; passing those warns).

    Bindings are registered automatically: any `{{...}}` in `action_config` (path, body,
    headers[].value, queryParameters[].value, ...) is detected and added to the query's
    `dynamicBindingPathList` so it actually evaluates — no more literal `{{ }}` going to the
    request ("Illegal character in path..."). Pass `dynamic_binding_paths` (a list of dotted
    keys relative to actionConfiguration) only to force extra paths. Literal values in
    Authorization/API-key headers are refused before reaching the browser; use a binding.
    `run_behaviour` (`MANUAL` default, `ON_PAGE_LOAD`, `AUTOMATIC`) is applied at creation.
    The Redux action list is refetched once at the end."""
    prepped, warnings_by_index = [], {}
    for i, q in enumerate(queries or []):
        entry, warns = _prep_query_entry(q)
        config = entry.get("action_config")
        if config is not None:
            if not isinstance(config, dict):
                raise ValueError("action_config deve ser um objeto")
            prepared, binding_paths = prepare_action_configuration(config)
            entry["action_config"] = prepared
            entry["dynamic_binding_paths"] = binding_paths + [
                p for p in (q.get("dynamic_binding_paths") or []) if p not in binding_paths
            ]
        else:
            entry.setdefault("dynamic_binding_paths", [])
        prepped.append(entry)
        if warns:
            warnings_by_index[i] = warns
    await ensure_ready()
    raw = await client.run_snippet(
        CREATE_QUERIES_JS,
        json_constants={
            "QUERIES": prepped,
            "DEFAULTS": QUERY_ACTION_CONFIG_DEFAULTS,
        },
    )
    if isinstance(raw, list):
        for i, r in enumerate(raw):
            if isinstance(r, dict) and i in warnings_by_index:
                r.setdefault("warnings", []).extend(warnings_by_index[i])
        return raw
    return []


@mcp.tool()
async def update_queries(updates: list[dict]) -> list:
    """Update multiple queries in one tool call. Each entry is `{"query_id",
    "action_config"?, "name"?, "run_behaviour"?, "dynamic_binding_paths"?, "datasource_id"?}`.
    `datasource_id` repoints the query at a saved datasource of the same plugin (e.g. move a
    REST query off an embedded/inline URL onto a shared datasource; its `path` stays relative
    to the datasource URL). (to change when a
    query runs prefer `set_run_behaviour`, which also refreshes the on-load set). `action_config`
    is shallow-merged into the existing actionConfiguration per entry, so you can change just
    `httpMethod` or `body` without re-sending the rest.

    For a REST POST/PUT JSON body, pass `json_body` (an object) — top-level or inside
    `action_config` — and it's serialized into the plugin's `body` string with smart `{{ }}`
    substitution and a `Content-Type: application/json` header (the plugin ignores n8n-style
    `sendBody`/`specifyBody`/`jsonBody`; passing those warns). Empty `{"key":"","value":""}` rows in
    headers/queryParameters are dropped so repeated updates don't accumulate blank rows.

    The query's `dynamicBindingPathList` is recomputed from the final actionConfiguration on
    every update, so `{{...}}` in path/body/headers/queryParameters is registered and actually
    evaluated (this also repairs queries that were saved without binding paths). Pass
    `dynamic_binding_paths` only to force extra dotted keys. Literal values in
    Authorization/API-key headers are refused before the update reaches the browser. The Redux
    action list is refetched once at the end."""
    await ensure_ready()
    query_ids = [u.get("query_id") for u in (updates or []) if isinstance(u, dict) and u.get("query_id")]
    current = await client.run_snippet(GET_QUERIES_JS, json_constants={"IDS": query_ids})
    current_by_id = {q.get("id"): q for q in (current or []) if isinstance(q, dict) and q.get("id")}
    prepped, warnings_by_index = [], {}
    for i, u in enumerate(updates or []):
        entry, warns = _prep_query_entry(u)
        existing = current_by_id.get(u.get("query_id"))
        if existing is not None:
            existing_config = existing.get("actionConfiguration") or {}
            patch_config = entry.get("action_config") or {}
            if not isinstance(existing_config, dict) or not isinstance(patch_config, dict):
                raise ValueError("action_config deve ser um objeto")
            # Merge here so the binding paths (and the secret check) cover the final config.
            prepared, binding_paths = prepare_action_configuration({**existing_config, **patch_config})
            entry["action_config"] = prepared
            entry["dynamic_binding_paths"] = binding_paths + [
                p for p in (u.get("dynamic_binding_paths") or []) if p not in binding_paths
            ]
        prepped.append(entry)
        if warns:
            warnings_by_index[i] = warns
    raw = await client.run_snippet(
        UPDATE_QUERIES_JS,
        json_constants={"UPDATES": prepped},
    )
    if isinstance(raw, list):
        for i, r in enumerate(raw):
            if isinstance(r, dict) and i in warnings_by_index:
                r.setdefault("warnings", []).extend(warnings_by_index[i])
        return raw
    return []


@mcp.tool()
async def execute_queries(
    query_ids: list[str],
    resolve_bindings: bool = True,
    max_rows: int = 50,
    timeout_seconds: int = 30,
    max_bytes: int = 40000,
    preview: bool = False,
    await_eval: bool = True,
) -> list:
    """Run only READ-ONLY queries by id and return their responses.

    Before dispatch, every action is checked by a fail-closed policy. SQL accepts only one
    `SELECT` or `WITH ... SELECT`; REST accepts GET/HEAD; GraphQL accepts queries; MongoDB
    accepts FIND/COUNT/DISTINCT and AGGREGATE without `$out`/`$merge`. Mutations, stored
    procedures, multiple SQL statements, unknown plugins, and ambiguous configurations are
    returned with `blocked=true` and are never dispatched.

    With `resolve_bindings=true` (default) the query runs through Appsmith's own Run action, so
    `{{...}}` bindings are evaluated against the current page state exactly like clicking Run;
    array bodies are capped at `max_rows` (`-1` for all; `rowCount` keeps the real size) and
    `timeout_seconds` bounds the wait. With `resolve_bindings=false` the saved action is executed
    through the REST API (`{ok, statusCode, isExecutionSuccess, body}` plus
    `messages`/`pluginErrorDetails`/`error`).

    With `await_eval` (default true, REST path), it first waits (bounded ~4s) for the eval worker to sync
    `appsmith.store` before running — so a query whose header/body binds `{{appsmith.store.*}}`
    doesn't resolve against a stale value right after `set_store` or a session-token refresh
    (feedback 3.2). If the worker doesn't confirm the sync in time, the result carries an
    `evalSyncWarning`. When you've just refreshed an auth/session token, run the query once more (or
    `refresh_page` first) if the first call still reports the old auth state.

    Large responses (e.g. a 150KB RSS feed) blow the tool-result token budget, so a `body`
    whose serialized size exceeds `max_bytes` (default 40000) is replaced with
    `{__truncated__: true, totalBytes, returnedBytes, preview}` — the head of the payload plus
    the real size, enough to inspect the shape without dumping the whole thing. Raise `max_bytes`
    to get more, or set `preview=True` to force a small sample (2KB) regardless.

    Note: `body` is the plugin's single returned result set. A stored procedure that emits
    several result sets (e.g. an intermediate `SELECT` before a final one) only exposes the
    last through this API — use `SET NOCOUNT ON` and return one result set to get what you
    expect."""
    await ensure_ready()
    decisions, allowed_ids = await _assess_queries(list(query_ids or []))

    raw = []
    if allowed_ids and resolve_bindings:
        raw = await client.run_snippet(
            RUN_ACTIONS_JS,
            json_constants={
                "ACTION_IDS": allowed_ids,
                "MAX_ROWS": int(max_rows),
                "TIMEOUT_MS": int(timeout_seconds) * 1000,
            },
        )
    elif allowed_ids:
        raw = await client.run_snippet(
            EXECUTE_QUERIES_JS,
            json_constants={"ACTION_IDS": allowed_ids, "AWAIT_EVAL": bool(await_eval)},
        )
    executed = [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []
    _truncate_bodies(executed, 2000 if preview else int(max_bytes))

    executed_by_id: dict[str, deque] = defaultdict(deque)
    for item in executed:
        if item.get("id"):
            executed_by_id[item["id"]].append(item)

    result: list[dict] = []
    for query_id, blocked in decisions:
        if blocked is not None:
            result.append(blocked)
        elif executed_by_id[query_id]:
            result.append(executed_by_id[query_id].popleft())
        else:
            result.append({
                "id": query_id,
                "ok": False,
                "blocked": False,
                "error": "A execução permitida não retornou resultado.",
            })
    return result


@mcp.tool()
async def set_page_load_actions(query_ids: list[str], enable: bool = True) -> dict:
    """Make queries run when the page loads (or stop them from doing so) — `set_run_behaviour`
    covers this and JS functions too. The
    capability that was missing (feedback §5: a query set to ON_PAGE_LOAD never fired because the
    page's `layoutOnLoadActions` was never regenerated, so panels/tables came up empty on open).

    For each id it sets the action's `runBehaviour` to `ON_PAGE_LOAD` (or `MANUAL` when
    `enable=False`), then re-saves the CURRENT page's layout so the Appsmith server recomputes
    `layoutOnLoadActions` — the actual on-load schedule the runtime executes. This replaces the
    custom-widget `onLoad`-event workaround.

    Targets must belong to the currently loaded page (the layout recompute is per-page) — switch_page
    to the page that owns the queries first. Returns `{results:[{id, name, runBehaviour}|{id,
    error}], layoutRecomputed, layoutOnLoadActions:[{id, name}]}` — `layoutOnLoadActions` is read
    back from the server so you can confirm the query is now scheduled. Takes effect on the next page
    load (refresh_page to see it run now)."""
    await ensure_ready()
    raw = await client.run_snippet(
        SET_PAGE_LOAD_ACTIONS_JS,
        json_constants={"ACTION_IDS": query_ids or [], "ENABLE": bool(enable)},
        js_helpers=PERSIST,
        wait_for_save=True,
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def set_run_behaviour(items: list[dict]) -> dict:
    """Set the "Run behaviour" of queries and JS functions — the editor's Manual / Automatic /
    On page load dropdown — on the current page (or package module).

    Each item is `{"query": <name|id>, "behaviour"}` or `{"js_object": <name|id>, "function":
    <name>, "behaviour"}`, with behaviour one of `MANUAL`, `ON_PAGE_LOAD`, `AUTOMATIC`,
    `ON_PAGE_UNLOAD`.

    Rule: MANUAL is the default — call the query/function from the event that needs it. Use
    ON_PAGE_LOAD only for what the screen must show when it opens. AUTOMATIC re-runs on EVERY
    change of anything it references (and on load), so it is refused unless the item carries a
    `reason` explaining why it must react automatically. `lint_design` flags every AUTOMATIC entity.

    The server recomputes the on-load set immediately (no layout save needed). Returns
    `{results:[{target, id, runBehaviour, reason?}|{error}], onLoad:[{id, name}]}`."""
    await ensure_ready()
    raw = await client.run_snippet(SET_RUN_BEHAVIOUR_JS, json_constants={"ITEMS": items or []})
    return raw if isinstance(raw, dict) else {"raw": raw}


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
async def dump_state(verbose: bool = False, sections: list[str] | None = None) -> dict:
    """Return the state of the currently open Appsmith application.

    Always returns `url`, `application`, `pages`, and `widgets` (the canvas as a
    nested tree of id/name/type/parent/position/children starting at MainContainer).
    With `verbose=False` (default) that lightweight shape is all you get.

    Pass `verbose=True` to also carry every property set on each widget node, plus
    top-level `datasources` (with connection storage), `queries` (with their
    actionConfiguration), `jsObjects` (with their bodies), and a derived
    `connections` list mapping widget property/trigger paths to the queries/JS
    objects/datasources they bind to by name.

    A full verbose dump can be large enough to blow the token budget. Narrow it with
    `sections` — any subset of `["widgets", "queries", "jsObjects", "datasources",
    "connections"]`; only those verbose sections are included (widget per-node
    `properties` are gated behind `"widgets"`). Omit `sections` (or pass an empty
    list) for the full verbose dump. A non-empty `sections` takes precedence over `verbose`
    (it enables just those sections even with `verbose=False`)."""
    await ensure_ready()
    raw = await client.run_snippet(
        DUMP_STATE_JS,
        json_constants={"VERBOSE": verbose, "SECTIONS": sections or []},
    )
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
async def list_icon_names(query: str | None = None) -> dict:
    """List valid `iconName` values for NATIVE icon-bearing widgets (ICON_WIDGET,
    ICON_BUTTON_WIDGET, BUTTON_WIDGET, MENU_BUTTON_WIDGET, and table `iconButton` columns).

    These are Blueprint (`@blueprintjs/icons`) names in kebab-case — a DIFFERENT set from the
    webfont (Tabler/Font Awesome) you load inside a Custom Widget. The same string can differ:
    `"robot"` renders in a custom widget's Tabler markup but is BLANK on a native ICON_WIDGET
    (an invalid iconName renders nothing, with no error). Pass `query` to filter by substring
    (e.g. "cart" → "shopping-cart", "arrow" → all arrows). If nothing matches for a native
    widget, use a Custom Widget with your own icon font instead.

    Returns `{count, iconSet: "blueprint", names}`."""
    names = find_icon_names(query)
    return {"count": len(names), "iconSet": "blueprint", "names": names}


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
    configure: list | None = None,
    from_schema: list | None = None,
    hide_unlisted: bool = False,
    allow_bindings: list[str] | None = None,
) -> dict:
    """Add, remove, reorder, configure, or seed columns on a TABLE_WIDGET_V2 in one call.

    - `add`: new columns. Each `{"id", "label"?, "columnType"?, "onClick"?, ...}` — defaults
      match Appsmith's "+" button. Numeric columns auto-align RIGHT; `id`/`*_id`/`id_*`
      columns start hidden (override with explicit `align`/`hidden`).
    - `configure`: tidy existing columns declaratively, no dotted paths:
      `[{"id", "label"?, "width"?, "align"?: "LEFT"|"CENTER"|"RIGHT", "hidden"?: bool,
      "columnType"?, "editable"?, "currencyCode"?, "decimals"?, "dateInputFormat"?,
      "dateOutputFormat"?}]`. Replaces the ~20-key dotted-path block. Ids that don't exist yet
      come back in `ignored` (primaryColumns only exists once the table has data — use
      `from_schema` or connect_widget_data).
    - `hide_unlisted`: hide every column not named in `configure`/`from_schema` — the "show
      only these" shortcut.
    - `from_schema`: seed columns before any data exists (a data-bound table only materializes
      columns once a row arrives). Each `{"id", "columnType"?}` builds a data-mirror column with
      the correct `[]`-fallback computedValue + binding paths, so columns render immediately.
    - `remove`: column ids to drop. `reorder`: desired full id order (unlisted keep trailing order).

    Action columns: pass `"onClick": "{{ ... }}"` (+ optional `"buttonLabel"`, `"buttonColor"`,
    `"buttonVariant"`, `"isDisabled"`, or `"columnType": "iconButton"` with `"iconName"`) to make an
    action column — defaults to `columnType: "button"` and registers the onClick as a trigger so it
    fires (a text column's onClick is evaluated as data → "Data fields cannot execute framework
    actions"). For a menu use `"columnType": "menuButton"` with `"menuItems"`. Inside the onClick,
    read the clicked row via `{{ <table>.triggeredRow }}` — NOT `selectedRow` (which doesn't change
    when an action button is clicked).

    Per-row dynamic cell props (`buttonLabel`/`buttonColor`/`buttonVariant`/`isDisabled`/`isCompact`)
    may reference the row directly, e.g. `"buttonLabel": "{{ currentRow.banido ? 'Reativar' :
    'Inativar' }}"` and `"buttonColor": "{{ currentRow.banido ? '#16A34A' : '#D97706' }}"` — they're
    auto-wrapped in `<table>.processedTableData.map((currentRow, currentIndex) => ( ... ))` and
    registered as bindings so they evaluate per row instead of rendering the literal `{{ currentRow…`
    text. A static value (no `{{ }}`) passes through unchanged. Any column handler (`on*`) is
    registered as a trigger.

    ROW_LEVEL inline edit (Save/Discard buttons): add an `editActions` column —
    `add=[{"id": "row_actions", "columnType": "editActions", "onSave": "{{ q_save.run() }}",
    "onDiscard": "{{ q_reload.run() }}", "saveLabel"?, "discardLabel"?}]`. Both handlers are
    required (a partial editActions column breaks the whole table, so it is refused into
    `rejected`); the table switches to `inlineEditingSaveOption: "ROW_LEVEL"`
    (`rowLevelEditEnabled`). Make data columns editable with `configure=[{"id", "editable": true}]`.

    A binding on a column property the column editor shows as a switch/dropdown/colour (e.g.
    `hidden`, `editable`, `align`, `columnType`) is refused, because that control cannot display
    code. Per-row expressions (`{{ currentRow... }}`), `computedValue` and inline-edit
    `validation` are the column editor's own format and always pass. Authorise anything else by
    path: `allow_bindings=["<widget_id>.primaryColumns.<col>.<prop>"]`."""
    await ensure_ready()
    column_problems, _ = validate_panel_writes(
        [
            {
                "label": f"{widget_id}.primaryColumns.{spec.get('id')}",
                "type": "TABLE_WIDGET_V2",
                "column_prop": True,
                "props": {k: v for k, v in spec.items() if k != "id"},
            }
            for spec in list(add or []) + list(configure or [])
            if isinstance(spec, dict) and spec.get("id")
        ],
        UI_CONTROLS_BY_TYPE,
        allow_bindings=allow_bindings,
    )
    if column_problems:
        raise ValueError(format_problems(column_problems, "manage_table_columns"))
    raw = await client.run_snippet(
        MANAGE_TABLE_COLUMNS_JS,
        json_constants={
            "WIDGET_ID": widget_id,
            "ADD": add or [],
            "REMOVE": remove or [],
            "REORDER": reorder or [],
            "CONFIGURE": configure or [],
            "FROM_SCHEMA": from_schema or [],
            "HIDE_UNLISTED": bool(hide_unlisted),
        },
        js_helpers=PERSIST,
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def connect_widget_data(
    widget_id: str,
    query: str,
    columns: list | None = None,
    hide_unlisted: bool = False,
    label_field: str | None = None,
    value_field: str | None = None,
) -> dict:
    """Connect a TABLE_WIDGET_V2 / SELECT_WIDGET / MULTI_SELECT_WIDGET_V2 to a query exactly like
    picking it in the property pane's Data dropdown — the preferred way to feed data to a native
    widget, so whoever maintains the page sees the query selected (not an empty field or a JS blob).

    `query` is the query name (or id) on the current page. The widget gets `{{<query>.data}}`
    (no JS mode). Put filtering/renaming/formatting in the query's SQL, not in the binding.

    Tables: data columns are generated from the query's last result the way the editor generates
    them (isDerived:false, `processedTableData.map` computedValue), with readable labels
    ("valor_total" → "Valor total"), id-like columns hidden, numbers right-aligned, ISO dates as
    date columns shown as DD/MM/YYYY [HH:mm], booleans as checkboxes. The table's custom (derived)
    columns are kept. Run the query first (execute_queries) so there is a result to read; with no
    result, pass `columns` to seed them. `columns` = `[{"id", "label"?, "columnType"?, "width"?,
    "align"?, "hidden"?, "currencyCode"?, "decimals"?, "dateInputFormat"?, "dateOutputFormat"?}]`
    refines the generated columns (currency defaults to BRL with 2 decimals) and sets their order
    first; `hide_unlisted` hides every data column not listed.
    When the editor has no result yet, a read-only SELECT is run once to learn the columns (a
    query that could write is never run).

    Selects: pass `label_field` / `value_field` (query column names) → `optionLabel`/`optionValue`;
    the sample default selection is cleared.

    Returns `{widgetId, query, tableData|sourceData, columns?, persisted}` or `{error}`."""
    await ensure_ready()

    async def run(sample):
        return await client.run_snippet(
            CONNECT_WIDGET_DATA_JS,
            json_constants={
                "WIDGET_ID": widget_id,
                "QUERY": query,
                "COLUMNS": columns or [],
                "HIDE_UNLISTED": bool(hide_unlisted),
                "LABEL_FIELD": label_field,
                "VALUE_FIELD": value_field,
                "SAMPLE": sample,
            },
            js_helpers=WIDGET_WRITE,
        )

    raw = await run(None)
    if isinstance(raw, dict) and raw.get("needsSample"):
        # The table needs one result to generate its columns. Run the query only when it passes
        # the read-only execution policy; never execute anything that could write.
        sample, note, res = [], None, None
        if raw.get("readOnly") and raw.get("instanceId"):
            decisions, allowed = await _assess_instances([raw["instanceId"]])
            if allowed:
                res = await _instances("run", {"instances": allowed})
            else:
                note = f"{query} was not run to read its columns: {decisions[0][1]['error']} — pass `columns`"
        elif raw.get("readOnly"):
            decisions, allowed = await _assess_queries([raw["queryId"]])
            if allowed:
                res = await client.run_snippet(EXECUTE_QUERIES_JS, json_constants={"ACTION_IDS": allowed, "AWAIT_EVAL": True})
            else:
                note = f"{query} was not run to read its columns: {decisions[0][1]['error']} — pass `columns`"
        if res is not None:
            first = res[0] if isinstance(res, list) and res else {}
            if isinstance(first.get("body"), list):
                sample = first["body"]
            else:
                note = f"running {query} to read its columns failed: {first.get('error')}"
        raw = await run(sample)
        if note and isinstance(raw, dict):
            raw["warning"] = note
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
        js_helpers=PERSIST,
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
    `field` is one of `html`, `css`, or `js`. `old` is matched literally first; if that
    fails it retries with a token-preserving normalized match (whitespace between tokens is
    ignored, but never inside strings/identifiers) so re-indented/prettified code still
    matches — the result reports `matchMode` (`literal` or `normalized`). If `old` occurs more
    than once the edit fails unless `replace_all` is true.

    To apply the SAME edit to several identical widgets in one call, pass `"widget_ids":
    [id1, id2, ...]` instead of `widget_id` — the edit is fanned out to each, with a per-widget
    result. Fan-out only reaches widgets on the CURRENTLY LOADED page: an id on another page returns
    an actionable "not found" telling you to switch_page first. For a component replicated across
    pages (e.g. a navbar as N custom widgets), the reliable pattern is: on each page, switch_page to
    it and apply the edit there — or edit one copy and, on that same page, sync_custom_widget to the
    others on that page. (For a large rewrite where matching `old` is fragile, prefer
    set_custom_widget_code, which replaces a whole field.)

    Per-edit result reports `replacements` (count) + `matchMode`, or an `error` (widget not
    found / wrong type / bad field / `old` not found / ambiguous match). The change is
    written to both `srcDoc` and `uncompiledSrcDoc` so a reload can't revert it;
    successful edits report `synced: true`."""
    await ensure_ready()
    # Fan an edit with `widget_ids` out into one edit per widget so the same change lands on
    # every replicated widget (e.g. a navbar copied across pages) in a single call.
    expanded = []
    for e in (edits or []):
        if isinstance(e.get("widget_ids"), list):
            for wid in e["widget_ids"]:
                expanded.append({**{k: v for k, v in e.items() if k != "widget_ids"}, "widget_id": wid})
        else:
            expanded.append(e)
    edits = expanded
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
            js_helpers=PERSIST,
            wait_for_save=True,
        )
        for r in results:
            if "error" not in r and r.get("widget_id") in updates:
                r["synced"] = True
    return results


@mcp.tool()
async def set_custom_widget_code(
    widget_ids: list[str],
    html: str | None = None,
    css: str | None = None,
    js: str | None = None,
) -> list:
    """Replace whole source fields of one or more Custom Widgets — the robust alternative to
    patch_widget_code when you're rewriting most of a field, or when matching `old` is fragile
    (Appsmith prettifies/reorders stored HTML). Only the fields you pass (`html`/`css`/`js`)
    are replaced; omitted fields are left untouched. Pass several `widget_ids` to write the
    same code to every replicated widget (e.g. a navbar copied across pages) in one call.

    Source is beautified, then written to both `srcDoc` and `uncompiledSrcDoc` so a reload
    can't revert it. Returns a per-widget result with `synced: true` (or an `error`, e.g. the
    id isn't a CUSTOM_WIDGET)."""
    await ensure_ready()
    src = {}
    if html is not None:
        src["html"] = format_source("html", html)
    if css is not None:
        src["css"] = format_source("css", css)
    if js is not None:
        src["js"] = format_source("js", js)
    if not src:
        return [{"error": "pass at least one of html/css/js"}]
    widgets = [{"widget_id": wid, "srcDoc": src} for wid in (widget_ids or [])]
    raw = await client.run_snippet(
        SYNC_WIDGET_SOURCE_JS,
        json_constants={"WIDGETS": widgets},
        js_helpers=PERSIST,
        wait_for_save=True,
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def sync_custom_widget(
    source_id: str,
    target_ids: list[str],
    copy_model: bool = True,
    copy_events: bool = True,
) -> dict:
    """Copy a Custom Widget's source onto one or more OTHER custom widgets — the fix for a
    component replicated across pages (e.g. a navbar that exists as N identical custom widgets).
    Edit the source once, then fan it out here instead of re-applying every edit N times.

    Always copies `srcDoc`/`uncompiledSrcDoc`; also copies `defaultModel` (when `copy_model`)
    and `events` + their trigger handlers (when `copy_events`), keeping each target's dynamic
    binding/trigger path lists consistent. Written through the layout PUT (survives reload) and
    the live client node (so later writes don't drop it). Returns
    `{source, targets:[{widget_id, name, synced}|{widget_id, error}]}`."""
    await ensure_ready()
    raw = await client.run_snippet(
        SYNC_CUSTOM_WIDGET_JS,
        json_constants={
            "SOURCE_ID": source_id,
            "TARGET_IDS": target_ids or [],
            "COPY_MODEL": bool(copy_model),
            "COPY_EVENTS": bool(copy_events),
        },
        js_helpers=PERSIST,
        wait_for_save=True,
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def create_custom_widget(
    html: str | None = None,
    css: str | None = None,
    js: str | None = None,
    default_model: dict | str | None = None,
    name: str | None = None,
    parent_id: str = "0",
    left: int | None = None,
    top: int | None = None,
    columns: int | None = None,
    rows: int | None = None,
    apply_theme: bool = True,
) -> dict:
    """Create a single Custom Widget (HTML/CSS/JS in an iframe).

    Build screens with NATIVE widgets first (tables, selects, inputs, charts, containers,
    modals) — they are what a maintainer can inspect and edit in the property pane. Use a Custom
    Widget only for what native widgets can't render (bespoke visuals, a navbar component...), and
    never as a wrapper to feed data to a table/list that a native widget could show.

    By default the widget is auto-sized to fill its parent canvas (full width, height
    measured from available pixels) at the top-left. Pass `parent_id` to place it inside a
    container/tabs canvas, and `left`/`top`/`columns`/`rows` to position/size it explicitly
    (e.g. a navbar: `top=0, rows=7`) — any omitted dimension keeps the auto value.

    `html`/`css`/`js` seed its source (omitted fields fall back to Appsmith's starter
    template). `default_model` seeds the data read via `appsmith.model` (dict or JSON string).

    IMPORTANT — model serialization at the iframe boundary: any NON-string model value arrives
    inside the widget as a JSON STRING, not its native type. A model entry bound to an array/
    object (`"{{ q.data }}"`), a boolean (`"{{ x.isLoading }}"`), or a number reads back as a
    string — so `appsmith.model.rows` is `"[{...}]"` (not an array) and `appsmith.model.loading`
    is `"false"` (a truthy string!). In the widget's JS, parse non-string fields defensively:
    `let rows = appsmith.model.rows; if (typeof rows === "string") { try { rows = JSON.parse(rows) }
    catch(e) { rows = [] } }` — and treat booleans as `String(v) === "true"`. Plain string bindings
    (e.g. a name) pass through untouched. (This is the Appsmith iframe contract, not something the
    MCP can change from here.)

    External data: a Custom Widget runs in a cross-origin sandboxed iframe, so a `fetch()` inside
    it to a CORS-restricted API is blocked (an RSS/news proxy fails; a CORS-open API like a currency
    or weather endpoint works). For CORS-restricted sources, create a server-side REST query
    (create_queries) — the Appsmith server makes the request (no CORS) — and feed its result into the
    widget's `default_model` (remembering the JSON-string boundary above), instead of fetching from
    the iframe.

    With `apply_theme` (default true) the widget is created frameless and blended into the app
    background (`borderWidth:0`, `boxShadow:"none"`, `backgroundColor` bound to the theme) so it
    doesn't get the default white frame. Seeded source is written to both `srcDoc` and
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
    if apply_theme:
        # Kill the default light-grey frame + white box that clashes with a themed app.
        props["borderWidth"] = 0
        props["boxShadow"] = "none"
        props["backgroundColor"] = "{{appsmith.theme.colors.backgroundColor}}"
    raw = await client.run_snippet(
        CREATE_CUSTOM_WIDGET_JS,
        json_constants={
            "PARENT_ID": parent_id, "PROPS": props, "NAME": name, "SRC": src, "SEED": seed,
            "LEFT": left, "TOP": top, "COLUMNS": columns, "ROWS": rows,
        },
        wait_for_save=True,
    )
    await client.run_snippet(
        SYNC_WIDGET_SOURCE_JS,
        json_constants={"WIDGETS": []},
        js_helpers=PERSIST,
        wait_for_save=True,
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def get_custom_widget(widget_id: str) -> dict:
    """Return a Custom Widget's full source (`srcDoc` html/css/js), `defaultModel`,
    events, name, and grid position. Errors if the id is not a CUSTOM_WIDGET."""
    await ensure_ready()
    # GET_WIDGET_JS closes over FIELDS and INCLUDE_SOURCE consts — inject both (with
    # include_source=true so srcDoc survives), else the snippet throws
    # "ReferenceError: FIELDS is not defined" and this tool crashes.
    raw = await client.run_snippet(
        GET_WIDGET_JS,
        json_constants={"WIDGET_ID": widget_id, "INCLUDE_SOURCE": True, "FIELDS": []},
    )
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
    string). NOTE: non-string model values arrive inside the widget as JSON strings — an
    array/object/boolean/number bound into the model reads back as a string, so parse defensively
    (`JSON.parse` for arrays/objects, `String(v) === "true"` for booleans). See
    create_custom_widget for the full contract. `name` renames it. `events` registers the event
    names the widget can emit
    (e.g. `["onRefresh"]`). `triggers` binds those events to expressions, keyed by event
    name (e.g. `{"onRefresh": "{{ bootstrap.load() }}"}`) — each is wired into the widget's
    dynamicTriggerPathList automatically. `dynamic_height` is `"AUTO_HEIGHT"` or `"FIXED"`.
    `left`/`top`/`columns`/`rows` move/resize it. If you pass `rows` together with
    `dynamic_height="AUTO_HEIGHT"`, `rows` is applied as `minDynamicHeight` (not a fixed
    height) so auto-height is preserved — otherwise a fixed row count silently forces FIXED and
    a growing widget (e.g. a navbar with a dropdown) gets clipped. Source code (html/css/js) is
    not editable here — use patch_widget_code for targeted in-place source edits."""
    await ensure_ready()
    props = {}
    if default_model is not None:
        props["defaultModel"] = default_model if isinstance(default_model, str) else json.dumps(default_model)
    if events is not None:
        props["events"] = events
    if dynamic_height is not None:
        props["dynamicHeight"] = dynamic_height
    result = {}
    # rows + explicit AUTO_HEIGHT conflict: honor auto-height, apply rows as the floor.
    rows_for_bounds = rows
    if dynamic_height == "AUTO_HEIGHT" and rows is not None:
        props["minDynamicHeight"] = int(rows)
        rows_for_bounds = None
        result["rowsAppliedAsMinHeight"] = int(rows)
    if props:
        raw = await client.run_snippet(
            UPDATE_WIDGETS_JS,
            json_constants={"UPDATES": [{"widget_id": widget_id, "props": props}]},
            js_helpers=WIDGET_WRITE,
            wait_for_save=True,
        )
        result["update"] = raw[0] if isinstance(raw, list) and raw else raw
        result["synced"] = True
    if triggers:
        # Wire event handlers in a SEPARATE update, AFTER `events` is declared, forcing the
        # keys into dynamicTriggerPathList (custom-widget event names need not start with
        # `on`). Bundling triggers with an `events` change makes Appsmith reclassify the
        # handler as a data field → "Data fields cannot execute framework actions".
        raw = await client.run_snippet(
            UPDATE_WIDGETS_JS,
            json_constants={"UPDATES": [{
                "widget_id": widget_id,
                "props": dict(triggers),
                "trigger_keys": list(triggers.keys()),
            }]},
            js_helpers=WIDGET_WRITE,
            wait_for_save=True,
        )
        result["triggers"] = raw[0] if isinstance(raw, list) and raw else raw
        result["synced"] = True
    if name is not None:
        raw = await client.run_snippet(
            RENAME_WIDGETS_JS,
            json_constants={"UPDATES": [{"widget_id": widget_id, "new_name": name}]},
            js_helpers=PERSIST,
            wait_for_save=True,
        )
        result["rename"] = raw[0] if isinstance(raw, list) and raw else raw
    if any(v is not None for v in (left, top, columns, rows_for_bounds)):
        bounds = {"widget_id": widget_id}
        if left is not None:
            bounds["left"] = int(left)
        if top is not None:
            bounds["top"] = int(top)
        if columns is not None:
            bounds["columns"] = int(columns)
        if rows_for_bounds is not None:
            bounds["rows"] = int(rows_for_bounds)
        raw = await client.run_snippet(
            SET_WIDGET_BOUNDS_JS,
            json_constants={"UPDATES": [bounds]},
            js_helpers=PERSIST,
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
        js_helpers=PERSIST,
        wait_for_save=True,
    )
    await client.run_snippet(
        SYNC_WIDGET_SOURCE_JS,
        json_constants={"WIDGETS": []},
        js_helpers=PERSIST,
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
    defaults to the currently open page. Waits for each create to land and returns its
    real `id` (or null), so you can immediately execute_js_functions / patch_js_objects."""
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
    `{"js_object_id", "body", "function_names"?}`. Appsmith re-parses each body into its
    member functions (adding/removing them) and persists — this tool waits for that
    re-parse to land before returning, so a follow-up execute_js_functions won't hit the
    stale version (no more delete+create workaround). If `function_names` is omitted, the
    top-level names are parsed from `body` and used to confirm the re-parse settled. Returns
    per-object `{id, name, functionNames, persisted}` (or `warning` if it didn't settle)."""
    await ensure_ready()
    resolved = []
    for u in updates or []:
        body = u.get("body", "")
        fns = u.get("function_names")
        names = fns if fns is not None else parse_function_names(body)
        resolved.append({
            "js_object_id": u.get("js_object_id"),
            "body": body,
            "function_names": names,
        })
    raw = await client.run_snippet(
        UPDATE_JS_OBJECTS_JS,
        json_constants={"UPDATES": resolved},
    )
    return raw if isinstance(raw, list) else []


@mcp.tool()
async def execute_js_functions(executions: list[dict]) -> list:
    """Blocked by the read-only execution policy: JS functions can indirectly run queries that
    write and other side effects. Validate JS with get_js_objects / get_eval_errors /
    eval_value, and let the user run the function in the editor."""
    return [
        {
            "jsObjectId": item.get("js_object_id"),
            "functionName": item.get("function_name"),
            "ok": False,
            "blocked": True,
            "error": (
                "Execução bloqueada: funções JavaScript podem produzir efeitos colaterais."
            ),
        }
        for item in (executions or [])
        if isinstance(item, dict)
    ]


@mcp.tool()
async def run_command(snippet: str) -> dict:
    """Blocked by the read-only execution policy: arbitrary JS could bypass it. Use the fixed
    read tools instead (find_widgets, list_widgets, list_children, get_widget, eval_value,
    get_store, get_queries, get_datasource, dump_state, get_eval_errors, get_render_health)."""
    return {
        "ok": False,
        "blocked": True,
        "error": (
            "Execução bloqueada: JavaScript arbitrário pode contornar "
            "a política somente leitura."
        ),
    }


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
    """Reload the attached Firefox tab and wait for it to finish loading. Resets the Redux
    store binding, so the next tool call re-bootstraps it.

    If the URL has an entity selected (`/widgets/<id>`, `/jsObjects/<id>`, `/queries/<id>`,
    `/datasources/<id>`), the reload drops that segment first and returns to the canvas: a selected
    widget narrows the canvas to ~320px, and a selected JS object / query / datasource opens the
    code editor — either makes a follow-up screenshot show the wrong thing when the layout is fine.

    Then waits for the page to settle — artboard up, no query in flight, no loading skeleton — so
    a follow-up screenshot shows the real screen. Returns `{reloaded, normalizedUrl, settled,
    pendingQueries}`."""
    global ready
    await ensure_ready()
    url = await client.get_url()
    base = re.sub(r"/(?:widgets|jsObjects|queries|datasources|api|datasource)/[^/?#]+", "", url) if isinstance(url, str) else None
    # The entity segment can carry a `?editName=true` (or similar) query that keeps the editor
    # focused after reload — drop the query string too once we've stripped an entity segment.
    if base and base != url:
        base = base.split("?", 1)[0].split("#", 1)[0]
    if base and base != url:
        await client.navigate(base)
        normalized = True
    else:
        await client.reload()
        normalized = False
    ready = False
    await ensure_ready()
    settle = await client.run_snippet(SETTLE_JS)
    settle = settle if isinstance(settle, dict) else {}
    return {"reloaded": await client.get_url(), "normalizedUrl": normalized, **settle}


@mcp.tool()
async def capture_screenshot(
    widget_id: str | None = None,
    scroll_to: str | None = None,
    full_page: bool = False,
) -> Image:
    """Capture a PNG screenshot of the attached Firefox tab for visual verification. Reuses the
    single BiDi session, so no extra browser is opened.

    By default captures the current viewport (which includes the editor chrome). Narrow it:
      - `widget_id`: scroll that widget into view and CROP to just it (with a little padding) —
        the cleanest way to inspect one widget without the surrounding editor panels.
      - `scroll_to`: scroll that widget into view, then capture the whole viewport — use to bring
        off-screen content on-screen (e.g. action columns on the right, a page footer below).
      - `full_page=True`: capture the entire scrollable document instead of just the viewport."""
    await ensure_ready()
    clip = None
    origin = None
    target = widget_id or scroll_to
    if target:
        rect = await client.run_snippet(SCROLL_WIDGET_JS, json_constants={"WIDGET_ID": target})
        if isinstance(rect, dict) and "error" in rect:
            raise RuntimeError(rect["error"])
        if widget_id and isinstance(rect, dict):
            pad = 8
            clip = {
                "type": "box",
                "x": max(0.0, rect["x"] - pad),
                "y": max(0.0, rect["y"] - pad),
                "width": rect["width"] + 2 * pad,
                "height": rect["height"] + 2 * pad,
            }
    if full_page:
        origin = "document"
        clip = None
    data = await client.capture_screenshot(clip=clip, origin=origin)
    if not data:
        raise RuntimeError("screenshot capture returned no data")
    return Image(data=base64.b64decode(data), format="png")


@mcp.tool()
async def screenshot() -> Image:
    """Alias of `capture_screenshot()` with no arguments: a PNG of what the attached tab is
    showing right now. The store having 55 widgets does not mean 55 widgets rendered."""
    return await capture_screenshot()


async def _preview_modal(modal_id: str) -> Image:
    """Open a modal at runtime, screenshot, and always close it again. SHOW_MODAL/CLOSE_MODAL
    are runtime-only (no persist), so this never dirties the saved page."""
    await client.run_snippet(TOGGLE_MODAL_JS, json_constants={"WIDGET_ID": modal_id, "OPEN": True})
    data = None
    try:
        await client.run_snippet(SETTLE_JS)
        data = await client.capture_screenshot()
    finally:
        try:
            await client.run_snippet(TOGGLE_MODAL_JS, json_constants={"WIDGET_ID": modal_id, "OPEN": False})
        except Exception:
            pass
    if not data:
        raise RuntimeError("no screenshot captured")
    return Image(data=base64.b64decode(data), format="png")


async def _preview_tab(tabs_id: str, tab: str) -> Image:
    """Render an inactive tab by temporarily flipping the tabs widget's defaultTab, persisting,
    reloading, screenshotting — then ALWAYS restoring the original defaultTab (even on error),
    so no dirty write is left behind."""
    global ready
    res = await client.run_snippet(
        SET_DEFAULT_TAB_JS,
        json_constants={"WIDGET_ID": tabs_id, "VALUE": tab, "RESOLVE": True},
    )
    if isinstance(res, dict) and res.get("error"):
        avail = f" — available tabs: {res.get('available')}" if res.get("available") else ""
        raise ValueError(res["error"] + avail)
    original = res.get("original")
    real_id = res.get("widgetId")
    data = None
    try:
        await _persist_layout()
        await client.reload()
        ready = False
        await ensure_ready()
        await client.run_snippet(SETTLE_JS)
        data = await client.capture_screenshot()
    finally:
        try:
            await client.run_snippet(
                SET_DEFAULT_TAB_JS,
                json_constants={"WIDGET_ID": real_id, "VALUE": original, "RESOLVE": False},
            )
            await _persist_layout()
            await client.reload()
            ready = False
            await ensure_ready()
        except Exception:
            pass
    if not data:
        raise RuntimeError("no screenshot captured")
    return Image(data=base64.b64decode(data), format="png")


@mcp.tool()
async def preview_hidden(widget_id: str, tab: str | None = None) -> Image:
    """Screenshot something normally not rendered, without leaving a dirty write — an inactive
    tab or a closed modal (both are absent from the DOM by design, so `get_render_health` and
    `capture_screenshot` can't show them).

    - MODAL_WIDGET: opens it at runtime, captures, closes it again (runtime-only, nothing is
      persisted).
    - TABS_WIDGET: pass `tab` (its id or label); temporarily flips defaultTab, reloads,
      captures, then restores the original defaultTab in a finally — the original is put back
      even if the capture fails.

    `widget_id` accepts a hex id or a widget name. Returns the PNG."""
    await ensure_ready()
    rec = await client.run_snippet(
        GET_WIDGET_JS,
        json_constants={"WIDGET_ID": widget_id, "INCLUDE_SOURCE": False, "FIELDS": ["type", "widgetId"]},
    )
    if not isinstance(rec, dict) or not rec.get("type"):
        raise ValueError(f"widget '{widget_id}' not found on the current page")
    wtype = rec.get("type")
    real_id = rec.get("widgetId")
    if wtype == "MODAL_WIDGET":
        return await _preview_modal(real_id)
    if wtype in ("TABS_WIDGET", "TABS_WIDGET_V2"):
        if not tab:
            raise ValueError("preview_hidden on a TABS_WIDGET needs `tab` (the tab's id or label)")
        return await _preview_tab(real_id, tab)
    raise ValueError(f"preview_hidden supports MODAL_WIDGET or TABS_WIDGET, not {wtype}")


@mcp.tool()
async def get_render_health() -> dict:
    """Compare what the DSL says exists against what actually rendered in the DOM.

    `get_state_summary` answers "is the widget in Redux", which is not the same question
    as "is the widget on screen" — a page can report 55 widgets while showing nothing.

    It waits for the page to settle first (no query in flight, no loading skeleton): `settled`
    says whether the wait completed and `pendingQueries` names anything still loading — if
    `settled` is false, re-read rather than trusting the numbers.

    Returns `widgetsInDsl` vs `widgetsRendered`, a `blankPage` flag, evaluation errors *with
    their text*, and two separate lists:
      - `problems` — genuine defects: missing from DOM, zero size, empty render, a table with
        columns configured but no header cells, or a column whose computedValue falls back to
        a bare identifier (throws ReferenceError while the table is empty).
      - `expected` — widgets legitimately absent because they are inside a closed modal, an
        inactive tab, or an isVisible:false subtree, each with the reason.

    Call this before telling anyone a screen is finished."""
    await ensure_ready()
    raw = await client.run_snippet(RENDER_HEALTH_JS)
    return raw if isinstance(raw, dict) else {"raw": raw}


def _dsl_summary(node: dict | None) -> dict | None:
    """A light structural tree of a DSL node: identity + grid box + children, dropping the
    heavy per-widget property payload so the shape fits in a response."""
    if not isinstance(node, dict):
        return None
    out = {
        "name": node.get("widgetName"),
        "id": node.get("widgetId"),
        "type": node.get("type"),
        "topRow": node.get("topRow"),
        "bottomRow": node.get("bottomRow"),
        "leftColumn": node.get("leftColumn"),
        "rightColumn": node.get("rightColumn"),
    }
    children = [_dsl_summary(c) for c in (node.get("children") or [])]
    children = [c for c in children if c]
    if children:
        out["children"] = children
    return out


@mcp.tool()
async def export_page(
    page_id: str | None = None,
    save_to_path: str | None = None,
    summary: bool = False,
) -> dict:
    """Return a page's complete persisted DSL as JSON — a snapshot you can restore with
    `import_page`.

    Take one before any risky batch: there is no undo for a layout write, and a page that
    stops loading cannot be repaired by deleting widgets. `page_id` defaults to the
    currently open page.

    The full DSL is hundreds of KB. To keep it out of the context window:
      - `save_to_path` writes the whole export (metadata + `dsl`) to a file and returns only
        `{savedTo, bytes, widgetCount, ...}` — grep the file, and restore later with
        `import_page(from_path=...)`.
      - `summary=true` returns a light structural tree (name/id/type/grid box + children) of
        every widget instead of the full property payload."""
    await ensure_ready()
    raw = await client.run_snippet(EXPORT_PAGE_JS, json_constants={"PAGE_ID": page_id})
    if not isinstance(raw, dict):
        return {"raw": raw}
    if "error" in raw:
        return raw
    meta_keys = ("applicationId", "pageId", "pageName", "layoutId", "widgetCount")
    if save_to_path:
        path = Path(save_to_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        meta = {k: raw.get(k) for k in meta_keys}
        meta["savedTo"] = str(path.resolve())
        meta["bytes"] = path.stat().st_size
        if summary:
            meta["tree"] = _dsl_summary(raw.get("dsl"))
        return meta
    if summary:
        return {k: raw.get(k) for k in meta_keys} | {"tree": _dsl_summary(raw.get("dsl"))}
    return raw


@mcp.tool()
async def import_page(
    dsl: dict | None = None,
    page_id: str | None = None,
    from_path: str | None = None,
) -> dict:
    """Overwrite a page's layout with a DSL previously returned by `export_page`.

    Pass the `dsl` dict directly, or `from_path` to load a file written by
    `export_page(save_to_path=...)` (the file's `dsl` field, or a bare DSL object). Replaces
    the whole widget tree — anything added since the snapshot is lost. Call `refresh_page`
    afterwards so the editor rebuilds from the restored DSL. `page_id` defaults to the
    currently open page."""
    await ensure_ready()
    if from_path:
        loaded = json.loads(Path(from_path).read_text(encoding="utf-8"))
        dsl = loaded.get("dsl", loaded) if isinstance(loaded, dict) else loaded
    if not isinstance(dsl, dict):
        return {"error": "no dsl to import — pass dsl=... or from_path to an export_page file"}
    raw = await client.run_snippet(
        IMPORT_PAGE_JS,
        json_constants={"DSL": dsl, "PAGE_ID": page_id},
        wait_for_save=True,
    )
    return raw if isinstance(raw, dict) else {"raw": raw}


# ---------------------------------------------------------------------------------------------
# Packages (code packages: query/JS modules; UI packages: UI modules) and their use on pages.
# ---------------------------------------------------------------------------------------------

DEFAULT_UI_MODULE_DSL = json.loads((Path(__file__).parent / "default_ui_module_dsl.json").read_text(encoding="utf-8"))


async def _packages(op: str, args: dict, confirm: bool = False):
    await ensure_ready()
    return await client.run_snippet(
        PACKAGES_JS,
        json_constants={"OP": op, "ARGS": args, "CONFIRM": bool(confirm), "DEFAULT_UI_DSL": DEFAULT_UI_MODULE_DSL},
    )


async def _instances(op: str, args: dict):
    await ensure_ready()
    return await client.run_snippet(
        MODULE_INSTANCES_JS,
        json_constants={"OP": op, "ARGS": args},
        js_helpers=PERSIST,
    )


@mcp.tool()
async def list_packages(workspace_id: str | None = None) -> list:
    """List the workspace's packages — code packages (`CODE`: query and JS modules) and UI packages
    (`UI`: UI modules). Returns `[{id, name, type, lastPublishedAt, modifiedAt, gitConnected,
    gitRepo?}]`. `workspace_id` defaults to the current workspace."""
    raw = await _packages("list", {"workspace_id": workspace_id})
    return raw if isinstance(raw, list) else [raw]


@mcp.tool()
async def get_package(package_id: str) -> dict:
    """Return a package and its modules: `{package, modules:[{id, name, type (QUERY_MODULE |
    JS_MODULE | UI_MODULE), moduleUUID, inputs:[{name, default}], outputs:[{name, value}],
    editorUrl}]}`. Open a module with `open_module` to edit its query/JS/widgets."""
    raw = await _packages("get", {"package_id": package_id})
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def open_module(package_id: str, module_id: str, timeout: int = 40) -> dict:
    """Open a package module in the editor (`/pkg/...` for code packages, `/ui-pkg/...` for UI
    packages) so the regular tools work on it:

    - query module: `get_queries` / `update_queries` / `execute_queries` edit its query;
    - JS module: `get_js_objects` / `update_js_objects` / `patch_js_objects`;
    - UI module: widget tools (`add_widgets`, `update_widgets`, `connect_widget_data`...) save to
      the module layout; `create_queries` / `create_js_objects` create module-level entities;
      `set_run_behaviour` / `set_page_load_actions` apply to the module.

    `get_build_context` then reports `context: "module"`. Inputs/outputs/name are edited with
    `update_module`; changes reach apps only after `publish_package`."""
    global ready
    info = await get_package(package_id)
    mod = next((m for m in (info.get("modules") or []) if m.get("id") == module_id), None)
    if not mod:
        return {"error": f"module {module_id} not found in package {package_id}", "package": info}
    await client.navigate(mod["editorUrl"])
    ready = False
    await ensure_ready()
    # The Redux store exists before the package editor finishes setting the module up; writing
    # earlier would target no module (queries would even ask for a pageId). Wait for it.
    ctx = None
    for _ in range(max(1, int(timeout * 2))):
        ctx = await client.run_snippet(GET_BUILD_CONTEXT_JS)
        if (isinstance(ctx, dict) and ctx.get("context") == "module" and ctx.get("moduleId") == module_id
                and ctx.get("ready")):
            if mod["type"] != "UI_MODULE" or ctx.get("rootChildren"):
                return {"opened": mod["name"], "type": mod["type"], "url": mod["editorUrl"], "context": ctx}
        await asyncio.sleep(0.5)
    return {"error": f"module editor did not finish loading {mod['name']} in {timeout}s — retry open_module",
            "url": mod["editorUrl"], "context": ctx}


@mcp.tool()
async def create_package(name: str, type: str = "CODE", module_name: str | None = None,
                         workspace_id: str | None = None) -> dict:
    """Create a package (on the dashboard pass `workspace_id` — list_workspaces).
    `type="CODE"` for query/JS modules (add them with `create_modules`);
    `type="UI"` creates it with a first UI module (`module_name`, default "UIModule1") exactly as
    the dashboard's "New UI package" does. Returns the package summary."""
    raw = await _packages("create", {"name": name, "type": type.upper(), "module_name": module_name,
                                     "workspace_id": workspace_id})
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def create_modules(package_id: str, modules: list[dict]) -> list:
    """Create modules in a package. Each entry:

    - `{"type": "QUERY", "name", "datasource_id" (id or name), "body"? (SQL), "action_config"?,
      "inputs"?}` — a query module; reference inputs as `{{inputs.<name>}}` in the body.
    - `{"type": "JS", "name", "body" (export default {...}), "function_names"?, "inputs"?}` — a JS
      module; functions start MANUAL.
    - `{"type": "UI", "name", "inputs"?, "outputs"?}` — an empty UI module (open it with
      `open_module` to build its widgets).

    `inputs` = `[{"name", "default"?}]`; `outputs` (UI) = `[{"name", "value": "{{widget.prop}}"}]`.
    Returns `[{id, name, type, moduleUUID}|{name, error}]`."""
    raw = await _packages("create_modules", {"package_id": package_id, "modules": modules or []})
    return raw if isinstance(raw, list) else [raw]


@mcp.tool()
async def update_module(module_id: str, name: str | None = None, inputs: list | None = None,
                        outputs: list | None = None) -> dict:
    """Edit a module's contract. `inputs` = full list `[{"name", "default"?}]` (existing fields keep
    their ids, so instance values survive); `outputs` (UI modules) = full list `[{"name", "value":
    "{{widget.prop}}"}]` — bindings are registered. `name` renames the module through Appsmith's
    refactor (references are rewritten). Publish afterwards for apps to see it."""
    raw = await _packages("update_module", {"module_id": module_id, "name": name,
                                            "inputs": inputs, "outputs": outputs})
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def publish_package(package_id: str, confirm: bool = False) -> dict:
    """Publish a package so apps can take the new version. This affects EVERY app that uses the
    package once they update (update_app_packages / editor prompt), so it only runs with
    `confirm=True` — ask the user first. Without it, returns an error describing the impact.
    Git-connected packages also need a commit through Appsmith's Git panel (reported as `warning`).
    Returns `{package, published, lastPublishedVersion}`."""
    raw = await _packages("publish", {"package_id": package_id}, confirm=confirm)
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def list_module_instances() -> dict:
    """On the current app page: the package module instances (`{id, name, type, module, inputs,
    outputs}`), the modules `available` to add (published packages of the workspace), and
    `packageUpdates` — `UPGRADABLE` when a newer published version is waiting
    (see update_app_packages). Query instances are used like queries (`{{name.data}}`,
    `{{name.run()}}`); JS instances like JS objects (`{{name.fn()}}`)."""
    raw = await _instances("list", {})
    return raw if isinstance(raw, dict) else {"raw": raw}


@mcp.tool()
async def add_module_instances(instances: list[dict]) -> list:
    """Add package modules to the current page. Each entry `{"module": <name|id|moduleUUID>,
    "name": <instance name>, "inputs"?: {<input>: <value or {{binding}}>}}`; UI modules also take
    `parent_id`, `left`, `top`, `columns`, `rows` (grid units) and are dropped as a module widget
    exactly like dragging them from the explorer. Returns `[{id, name, type, module, widgetId?,
    inputs?}|{error}]`. Feed a query instance to a table with `connect_widget_data`."""
    raw = await _instances("add", {"instances": instances or []})
    return raw if isinstance(raw, list) else [raw]


@mcp.tool()
async def run_module_instances(instances: list[str], max_bytes: int = 40000) -> list:
    """Run query-module instances of the current page (by name or id) the way their Run button
    does — the editor evaluates the instance inputs — and return `[{name, ok, body, error?}]`. The
    result also becomes `{{<instance>.data}}` in the editor. Bodies larger than `max_bytes` are
    truncated like execute_queries.

    The same fail-closed read-only policy as execute_queries applies: each instance's public
    query is read and assessed first; an instance that could write (or whose query can't be
    read) comes back with `blocked=true` and is never run."""
    await ensure_ready()
    refs = list(instances or [])
    decisions, allowed = await _assess_instances(refs)
    ran = []
    if allowed:
        raw = await _instances("run", {"instances": allowed})
        if not isinstance(raw, list):
            return [raw]
        ran = raw
    _truncate_bodies(ran, int(max_bytes))
    ran_iter = iter(ran)
    out = []
    for _ref, blocked in decisions:
        out.append(blocked if blocked is not None else next(ran_iter, {"ok": False, "error": "no result"}))
    return out


@mcp.tool()
async def update_module_instances(updates: list[dict]) -> list:
    """Set input values on module instances of the current page. Each entry
    `{"instance": <name|id>, "inputs": {<input>: <value or {{binding}}>}}` — merged into the
    current inputs."""
    raw = await _instances("update", {"updates": updates or []})
    return raw if isinstance(raw, list) else [raw]


@mcp.tool()
async def delete_module_instances(instances: list[str]) -> list:
    """Remove module instances (by name or id) from the current page; a UI instance's module widget
    is removed with it."""
    raw = await _instances("delete", {"instances": instances or []})
    return raw if isinstance(raw, list) else [raw]


@mcp.tool()
async def delete_packages(package_ids: list[str], confirm: bool = False) -> list:
    """Delete packages permanently. Every app still holding an instance of one of their modules
    breaks, and there is no undo, so this requires `confirm=true` — ask the user first.
    Returns `[{id, ok, error?}]`."""
    if not confirm:
        raise ValueError(
            "delete_packages: pass confirm=true — deleting a package is irreversible and breaks "
            "every app that still uses its modules. List them with list_module_instances first."
        )
    raw = await _packages("delete_package", {"ids": package_ids})
    return raw if isinstance(raw, list) else [raw]


@mcp.tool()
async def delete_modules(module_ids: list[str], confirm: bool = False) -> list:
    """Delete modules from their package. Instances of a deleted module stop working in every
    app that uses it, so this requires `confirm=true`. Publish the package afterwards for the
    removal to reach apps. Returns `[{id, ok, error?}]`."""
    if not confirm:
        raise ValueError(
            "delete_modules: pass confirm=true — instances of a deleted module stop working in "
            "every app that uses it."
        )
    raw = await _packages("delete_module", {"ids": module_ids})
    return raw if isinstance(raw, list) else [raw]


@mcp.tool()
async def update_app_packages() -> dict:
    """Bring the current app's module instances to the latest published package versions (the
    editor's "update packages" action). No-op when already up to date. Returns
    `{before, after, instancesUpdated}` — then refresh_page."""
    raw = await _instances("pull", {})
    return raw if isinstance(raw, dict) else {"raw": raw}


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
