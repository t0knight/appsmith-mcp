"""Keep every widget configuration visible in the Appsmith property pane.

A property whose pane control is visual (switch, dropdown, colour picker, data selector)
cannot render `{{ }}` code in that control. Writing a binding there leaves whoever maintains
the page looking at an empty or wrong-looking field while the real value hides in the DSL —
and the debugger shows nothing, because it is not an error.

`lint_design` already reports this after the fact (`binding_hidden_in_ui`). This module is the
same judgement applied *before* the write, so the page never reaches that state.

Three binding shapes are exempt, because for them the binding IS the native control:

  - the one-click data selector shows `{{query.data}}` as the chosen query in its dropdown;
  - the colour picker shows an `{{appsmith.theme...}}` value as the selected theme token;
  - a table column's `computedValue`/`validation` and its per-row props (`buttonColor`,
    `isDisabled`, ...) are evaluated against `currentRow` by the column editor itself —
    `manage_table_columns` wraps them in `processedTableData.map(...)` on purpose.

Conditional visibility is NOT exempt: Appsmith's own docs describe it as turning on the JS
toggle next to the Visible switch, so it is legitimate but must be authorised by path, and
written with that toggle on so the code shows in the pane.
"""

import re

FREE = "FREE"
LITERAL = "LITERAL"
NATIVE_BINDING = "NATIVE_BINDING"
HIDDEN_BINDING = "HIDDEN_BINDING"

ONE_CLICK = "ONE_CLICK_BINDING_CONTROL"

_BINDING_RE = re.compile(r"\{\{[\s\S]*?\}\}")
_QUERY_DATA_RE = re.compile(r"^\{\{\s*[A-Za-z_$][\w$]*\.data\s*\}\}$")
_THEME_RE = re.compile(r"^\{\{\s*appsmith\.theme\.[^{}]*\}\}$")
# The column editor evaluates these per row; `manage_table_columns` wraps them in
# processedTableData.map((currentRow, currentIndex) => ...), and inline-edit validation runs
# against editedValue/isNewRow. Both are how the pane itself stores a column.
_ROW_SCOPE_RE = re.compile(r"\b(currentRow|currentIndex|isNewRow|editedValue)\b")

# Column properties that exist only as a binding — they have no literal form at all.
COLUMN_NATIVE_PROPS = frozenset({"computedValue", "validation"})

# A column's own pane controls. `UI_CONTROLS_BY_TYPE` is derived from the WIDGET schema, which
# does not describe columns, so the column editor gets its own map. It carries both the real
# property names and the friendly ones `manage_table_columns(configure=...)` accepts, because a
# caller authorises the name they typed.
COLUMN_VISUAL_CONTROLS = {
    "isVisible": "SWITCH",
    "hidden": "SWITCH",
    "isDisabled": "SWITCH",
    "isCellVisible": "SWITCH",
    "isCellEditable": "SWITCH",
    "editable": "SWITCH",
    "isCompact": "SWITCH",
    "enableFilter": "SWITCH",
    "enableSort": "SWITCH",
    "align": "DROP_DOWN",
    "horizontalAlignment": "DROP_DOWN",
    "verticalAlignment": "DROP_DOWN",
    "columnType": "DROP_DOWN",
    "buttonVariant": "DROP_DOWN",
    "iconAlign": "DROP_DOWN",
    "sticky": "DROP_DOWN",
    "textColor": "COLOR_PICKER",
    "cellBackground": "COLOR_PICKER",
    "buttonColor": "COLOR_PICKER",
    "menuColor": "COLOR_PICKER",
}


def _has_binding(value) -> bool:
    return isinstance(value, str) and bool(_BINDING_RE.search(value))


def classify_value(widget_type, prop, value, ui_controls, *, column_prop=False) -> str:
    """Say how a single property write would land in the property pane.

    Returns `LITERAL` (the target), `FREE` (the pane already shows a code field, so there is
    nothing to hide), `NATIVE_BINDING` (the binding is the native control) or
    `HIDDEN_BINDING` (the pane would show a visual control that cannot display the code).
    """
    if not _has_binding(value):
        return LITERAL

    if column_prop:
        # Per-row props and computed/validation expressions are how the column editor itself
        # stores a column, so they stay native regardless of which control shows them.
        if prop in COLUMN_NATIVE_PROPS or _ROW_SCOPE_RE.search(value):
            return NATIVE_BINDING
        control = COLUMN_VISUAL_CONTROLS.get(prop)
        return HIDDEN_BINDING if control else FREE

    control = (ui_controls.get(widget_type) or {}).get(prop)
    if not control:
        return FREE

    if control == ONE_CLICK and _QUERY_DATA_RE.match(value):
        return NATIVE_BINDING
    if _THEME_RE.match(value):
        return NATIVE_BINDING
    return HIDDEN_BINDING


def _advice(prop: str, control: str, path: str) -> str:
    if control == ONE_CLICK:
        return (
            f"'{prop}' feeds the pane's Data selector, which only shows the query when the "
            f"value is exactly {{{{query.data}}}} — move the shaping into the query and connect "
            f'it with connect_widget_data, or authorise the code with allow_bindings=["{path}"]'
        )
    return (
        f"'{prop}' is shown by the pane as a {control} control, which cannot display code — "
        f"the field would look empty to whoever maintains the page. Write a literal value; if "
        f"the condition is genuinely needed, check the Appsmith docs for a native way first, "
        f'then authorise the exact path with allow_bindings=["{path}"]'
    )


def validate_panel_writes(entries, ui_controls, *, allow_bindings=None):
    """Check a batch of property writes before anything is applied.

    `entries` are `{"label", "type", "props", "column_prop"?}`; `label` is the widget name used
    to build the `Widget.prop` path a caller authorises. Returns `(problems, authorized_paths)`.
    `problems` are blocking lines in the shape `validation.format_problems` renders.
    """
    allowed = set(allow_bindings or ())
    problems: list[str] = []
    authorized: list[str] = []

    for entry in entries or []:
        widget_type = entry.get("type") or ""
        label = entry.get("label") or widget_type
        column_prop = bool(entry.get("column_prop"))
        for prop, value in (entry.get("props") or {}).items():
            verdict = classify_value(
                widget_type, prop, value, ui_controls, column_prop=column_prop
            )
            if verdict != HIDDEN_BINDING:
                continue
            path = f"{label}.{prop}"
            if path in allowed:
                authorized.append(path)
                continue
            control = (
                COLUMN_VISUAL_CONTROLS.get(prop)
                if column_prop
                else (ui_controls.get(widget_type) or {}).get(prop)
            ) or "visual"
            problems.append(f"{label} ({widget_type}): {_advice(prop, control, path)}")

    return problems, authorized
