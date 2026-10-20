"""Guard rails for widget property writes.

`update_widgets` persists whatever it is given by rewriting the page DSL. That makes it
possible to write properties the layout engine owns (`bottomRow`, `dynamicHeight`) or
that a dedicated tool builds (`primaryColumns`, `tabsObj`), producing states the editor
itself could never create. Those writes are accepted silently and only surface later as
a blank widget or an unloadable page — with `errors: []` in the debugger.

This module rejects those writes up front and points at the tool that does it properly.
"""

import difflib
import re

# Known sub-properties of a TABLE_WIDGET_V2 `primaryColumns.<col>` entry. Finite and stable,
# so a dotted `primaryColumns.id.computedValue` write is validated against THIS set instead
# of the widget's top-level schema — where it never matches, producing a line of false "not
# in the known schema" noise per column property (40 in one reported call) that buries any
# real warning. The dotted path is the documented, working way to configure a column.
TABLE_COLUMN_PROPS: frozenset[str] = frozenset({
    "label", "isVisible", "isDisabled", "isCellVisible", "width", "columnType",
    "horizontalAlignment", "verticalAlignment", "computedValue", "isDerived",
    "isEditable", "isCellEditable", "isSaveVisible", "isDiscardVisible", "isCompact",
    "selectOptions", "allowSameOptionsInNewRow", "onSubmit", "onOptionChange",
    "onClick", "onItemClicked", "outputFormat", "inputFormat", "allowCellWrapping",
    "textColor", "textSize", "fontStyle", "cellBackground", "sticky", "alias",
    "enableFilter", "enableSort", "currencyCode", "decimals", "thousandSeparator",
    "notation", "displayText", "validation", "menuItems", "iconName", "iconAlign",
    "buttonLabel", "buttonColor", "menuColor", "borderRadius", "boxShadow", "originalId",
    "placeholderText", "resetFilterTextOnClose", "buttonVariant", "menuVariant",
    "iconButtonStyle", "imageSize", "objectFit", "isCellEditable", "index",
})

# The event an editable/actionable column type actually fires. Setting the wrong one is
# accepted by the write but never runs — a `select` column wired to `onSubmit` was the single
# biggest reported time sink. Keyed by columnType.
COLUMN_EVENT_BY_TYPE: dict[str, str] = {
    "select": "onOptionChange",
    "button": "onClick",
    "iconButton": "onClick",
    "menuButton": "onItemClicked",
    "text": "onSubmit", "number": "onSubmit", "date": "onSubmit",
    "currency": "onSubmit", "url": "onSubmit", "phoneNumber": "onSubmit",
}
_COLUMN_EVENTS: frozenset[str] = frozenset({"onSubmit", "onOptionChange", "onClick", "onItemClicked"})
_PRIMARY_COLUMN_RE = re.compile(r"^primaryColumns\.([^.]+)\.(.+)$")

# The label property name differs by widget (INPUT/DATE use `label`, SELECT uses `labelText`).
# When the caller uses the wrong one *and the widget really has the other*, we remap instead
# of refusing — the correct name is unambiguous, so a refusal would just cost a round-trip.
LABEL_SYNONYMS: dict[str, str] = {"label": "labelText", "labelText": "label"}


def resolve_label_synonyms(props: dict, known: set[str]) -> dict[str, str]:
    """Return `{wrong_name: right_name}` for label props given under the wrong synonym for
    this widget, where the right name is a real property and the wrong one is not."""
    remaps: dict[str, str] = {}
    for prop in list(props or {}):
        if prop in known:
            continue
        alt = LABEL_SYNONYMS.get(prop)
        if alt and alt in known and alt not in props:
            remaps[prop] = alt
    return remaps


# Properties `update_widgets` must never write, mapped to the tool that owns them.
# Writing any of these persists a UI-impossible state whose failure shows up on the next
# page load, far from the call that caused it.
BLOCKED_PROPS: dict[str, str] = {
    # Grid geometry — recomputed by the layout engine from the widget tree.
    "topRow": "geometry is owned by the layout engine — use set_widget_bounds(top=...)",
    "bottomRow": "geometry is owned by the layout engine — use set_widget_bounds(rows=...)",
    "leftColumn": "geometry is owned by the layout engine — use set_widget_bounds(left=...)",
    "rightColumn": "geometry is owned by the layout engine — use set_widget_bounds(columns=...)",
    "originalTopRow": "auto-height bookkeeping — use set_widget_bounds(rows=...)",
    "originalBottomRow": "auto-height bookkeeping — use set_widget_bounds(rows=...)",
    "mobileTopRow": "responsive geometry is derived — use set_widget_bounds(top=...)",
    "mobileBottomRow": "responsive geometry is derived — use set_widget_bounds(rows=...)",
    "mobileLeftColumn": "responsive geometry is derived — use set_widget_bounds(left=...)",
    "mobileRightColumn": "responsive geometry is derived — use set_widget_bounds(columns=...)",
    "parentColumnSpace": "snap grid is derived from the parent canvas",
    "parentRowSpace": "snap grid is derived from the parent canvas",
    # Height mode — set_widget_bounds flips this to FIXED itself when you pass rows.
    "dynamicHeight": "height mode is owned by the layout engine — set_widget_bounds(rows=...) switches it to FIXED for you",
    "minDynamicHeight": "auto-height bounds are derived — use set_widget_bounds(rows=...)",
    "maxDynamicHeight": "auto-height bounds are derived — use set_widget_bounds(rows=...)",
    # Tree structure.
    "parentId": "use reparent_widgets(new_parent_id=...)",
    "children": "use add_widgets / delete_widgets / reparent_widgets",
    "widgetId": "immutable",
    "type": "immutable — delete the widget and add it again with the new type",
    "widgetName": "use rename_widgets(new_name=...)",
    # Built by a dedicated tool that knows the full required shape.
    "primaryColumns": (
        "use manage_table_columns(add=/remove=/reorder=) — a hand-written primaryColumns "
        "renders an empty table with no error, because each column needs id/alias/index/"
        "computedValue plus a dynamicBindingPathList entry"
    ),
    "columnOrder": "use manage_table_columns(reorder=[...])",
    "tabsObj": "use manage_tabs(add=/remove=/reorder=) — it also creates the child canvases",
    # Maintained automatically from the values you pass.
    "dynamicBindingPathList": "managed automatically — pass the {{...}} value itself",
    "dynamicTriggerPathList": "managed automatically — pass the on* handler itself",
    "dynamicPropertyPathList": "managed automatically",
}

# Valid on essentially every widget but not always present in the dumped schema or on a
# freshly created widget's Redux record.
UNIVERSAL_PROPS: frozenset[str] = frozenset({
    "isVisible", "isDisabled", "isLoading", "animateLoading", "tooltip",
    "borderRadius", "boxShadow", "accentColor", "backgroundColor",
})

# Defaults that silently change behaviour, surfaced by add_widgets so they don't have to
# be discovered by debugging an empty result set.
SIDE_EFFECT_DEFAULTS: dict[str, dict[str, str]] = {
    "DATE_PICKER_WIDGET2": {
        "defaultDate": "starts at today, not empty — pass defaultDate:'' so filters don't silently exclude everything",
    },
    "DATE_PICKER_WIDGET": {
        "defaultDate": "starts at today, not empty — pass defaultDate:'' to start blank",
    },
    "TABLE_WIDGET_V2": {
        "tableData": "starts empty; primaryColumns only exists after tableData has rows, so bind tableData and run the query before calling manage_table_columns",
    },
    "SELECT_WIDGET": {
        "sourceData": "ships with sample options — bind sourceData plus optionLabel/optionValue",
    },
}


def _suggest(prop: str, known: set[str]) -> list[str]:
    """Closest property names to `prop`, best guess first.

    difflib alone ranks by raw similarity, which puts `labelTextSize` above `label` for
    `labelText`. Prefer candidates that share a prefix with what was typed and are closest
    in length — that is nearly always the property the caller meant."""
    matches = difflib.get_close_matches(prop, sorted(known), n=5, cutoff=0.7)
    lowered = prop.lower()
    return sorted(
        matches,
        key=lambda m: (
            not (m.lower().startswith(lowered) or lowered.startswith(m.lower())),
            abs(len(m) - len(prop)),
            m,
        ),
    )[:3]


def _known_props(widget_type: str, live_keys: list[str] | None, widget_props: dict) -> tuple[set[str], bool]:
    """Return the property names considered valid for a widget, plus whether the schema
    is known to be incomplete.

    The live Redux record is the most reliable source: it carries properties inherited
    from base widgets that the dumped schema misses (INPUT_WIDGET_V2 spreads
    BaseInputWidget.getDefaults(), which is where its `label` comes from)."""
    schema = widget_props.get(widget_type) or {}
    defaults = schema.get("defaults") or {}
    meta = schema.get("metaProperties") or []
    known: set[str] = set(live_keys or [])
    known |= set(defaults.keys())
    known |= set((schema.get("properties") or {}).keys())
    known |= set(meta if isinstance(meta, list) else meta.keys())
    known |= UNIVERSAL_PROPS
    known.discard("__spreads__")
    # The dumped schema is incomplete for widgets that spread a base widget's defaults
    # (the input family), but the live Redux record already lists those inherited
    # properties — so the union is only untrustworthy when there is no live record.
    incomplete = not schema or ("__spreads__" in defaults and not live_keys)
    return known, incomplete


def validate_widget_updates(
    updates: list[dict],
    described: list[dict],
    widget_props: dict,
    *,
    allow_unknown: bool = False,
) -> tuple[list[str], list[dict]]:
    """Check a batch of `update_widgets` entries before anything is written.

    Returns `(problems, warnings)`. `problems` are blocking: each is a formatted line
    naming the widget, the property, and the tool to use instead. `warnings` are
    non-blocking notes attached to the per-widget results.

    A property is blocking when it is layout-engine owned, or when it does not exist on
    the widget *and* a close match does — `labelText` on an INPUT_WIDGET_V2 is a typo for
    `label`, and writing it stores text no renderer reads. Unknown properties with no
    close match only warn: the dumped schema can lag the running Appsmith version.
    """
    by_id = {d.get("widgetId"): d for d in (described or []) if isinstance(d, dict)}
    problems: list[str] = []
    warnings: list[dict] = []

    for entry in updates or []:
        widget_id = entry.get("widget_id")
        props = entry.get("props") or {}
        info = by_id.get(widget_id)
        if info is None or info.get("missing"):
            problems.append(f"{widget_id}: widget not found on the current page")
            continue

        widget_type = info.get("type") or ""
        name = info.get("name") or widget_id
        known, schema_incomplete = _known_props(widget_type, info.get("keys"), widget_props)
        column_types = info.get("columns") or {}

        for prop in props:
            if prop in BLOCKED_PROPS:
                problems.append(f"{name} ({widget_type}): '{prop}' — {BLOCKED_PROPS[prop]}")
                continue
            col_match = _PRIMARY_COLUMN_RE.match(prop)
            if col_match and widget_type == "TABLE_WIDGET_V2":
                col_id, sub = col_match.group(1), col_match.group(2)
                leaf = sub.split(".")[0]
                if leaf not in TABLE_COLUMN_PROPS:
                    warnings.append({
                        "widgetId": widget_id,
                        "warning": f"'{prop}': '{leaf}' is not a known TABLE_WIDGET_V2 column "
                                   f"property — check the spelling.",
                    })
                elif leaf in _COLUMN_EVENTS:
                    ctype = column_types.get(col_id)
                    expected = COLUMN_EVENT_BY_TYPE.get(ctype)
                    if expected and leaf != expected:
                        warnings.append({
                            "widgetId": widget_id,
                            "warning": f"'{prop}': a '{ctype}' column fires '{expected}', not "
                                       f"'{leaf}' — the handler is stored but never runs. "
                                       f"Use primaryColumns.{col_id}.{expected}.",
                        })
                continue
            if prop in known or prop.startswith("on"):
                continue
            suggestions = _suggest(prop, known)
            if suggestions and not schema_incomplete and not allow_unknown:
                problems.append(
                    f"{name} ({widget_type}): '{prop}' is not a property of {widget_type} — "
                    f"did you mean {' or '.join(repr(s) for s in suggestions)}?"
                )
            else:
                hint = f" did you mean {' or '.join(repr(s) for s in suggestions)}?" if suggestions else ""
                warnings.append({
                    "widgetId": widget_id,
                    "warning": f"'{prop}' is not in the dumped schema for {widget_type} "
                               f"(the schema can lag the running version); it is written "
                               f"as-is.{hint}",
                })

    return problems, warnings


def validate_new_widget_props(widgets: list[dict], widget_props: dict) -> tuple[list[str], list[dict]]:
    """Same guard for `add_widgets`, where the widget does not exist yet.

    Only blocked properties are fatal here: without a live Redux record the known-property
    set is the dumped schema alone, which is too thin to reject a typo confidently.
    Geometry belongs in the `left`/`top`/`columns`/`rows` arguments, so writing it through
    `props` is always a mistake."""
    problems: list[str] = []
    warnings: list[dict] = []
    for index, spec in enumerate(widgets or []):
        widget_type = spec.get("widget_type") or ""
        label = spec.get("name") or f"widgets[{index}]"
        known, _ = _known_props(widget_type, None, widget_props)
        for prop in spec.get("props") or {}:
            if prop in BLOCKED_PROPS:
                hint = BLOCKED_PROPS[prop]
                if prop in ("topRow", "bottomRow", "leftColumn", "rightColumn"):
                    hint = "pass left/top/columns/rows as arguments instead of props"
                problems.append(f"{label} ({widget_type}): '{prop}' — {hint}")
            elif prop not in known and not prop.startswith("on"):
                suggestions = _suggest(prop, known)
                hint = f" did you mean {' or '.join(repr(s) for s in suggestions)}?" if suggestions else ""
                warnings.append({
                    "widget": label,
                    "warning": f"'{prop}' is not in the known schema for {widget_type}.{hint}",
                })
    return problems, warnings


def side_effect_notes(widget_type: str, props: dict | None) -> list[str]:
    """Defaults worth reporting back for a widget that was just created, unless the caller
    already set them."""
    given = set((props or {}).keys())
    return [
        f"{prop}: {note}"
        for prop, note in (SIDE_EFFECT_DEFAULTS.get(widget_type) or {}).items()
        if prop not in given
    ]


def format_problems(problems: list[str], tool: str) -> str:
    """Render blocking problems as an error message that says what to do next."""
    lines = "\n".join(f"  - {p}" for p in problems)
    return (
        f"{tool}: refused {len(problems)} property write(s); nothing was applied.\n"
        f"{lines}\n"
        f"Fix the call, or pass force=true to write anyway (this can corrupt the page)."
    )
