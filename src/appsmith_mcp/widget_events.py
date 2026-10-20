"""Build widget event handlers the way the property pane's action selector stores them.

The pane shows a dropdown — Execute a query, Show alert, Navigate to, ... — only while the
handler is a single recognised call. Anything richer (a `.then()` chain, a custom expression)
is still valid and still written, but the pane falls back to showing raw code. So every
handler reports which of the two it produced, instead of silently turning a field the builder
expected to click through into code they have to read.

Taking the action as a dict rather than a string is what makes that judgement possible: the
caller says what they want to happen, and the exact syntax the selector recognises is built
here, once.
"""

import json

# Fields each action needs, for an error that names what is missing instead of raising KeyError.
_REQUIRED = {
    "run_query": ("query",),
    "run_js": ("object", "function"),
    "show_alert": ("message",),
    "show_modal": ("modal",),
    "close_modal": ("modal",),
    "navigate_to": (),
    "store_value": ("key", "value"),
    "clear_store": (),
    "download": ("data", "name"),
    "copy_to_clipboard": ("text",),
    "reset_widget": ("widget",),
    "set_interval": ("callback",),
    "clear_interval": ("id",),
    "post_message": ("message",),
}

SUPPORTED_ACTIONS = tuple(_REQUIRED)


def _q(value) -> str:
    """Quote a JS string literal the way the action selector writes one."""
    text = "" if value is None else str(value)
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _call(spec: dict) -> str:
    """The bare JS call for one action spec, without the `{{ }}` wrapper."""
    action = spec.get("action")
    required = _REQUIRED.get(action)
    if required is None:
        raise ValueError(
            f"set_widget_events: unknown action {action!r} — supported: "
            f"{', '.join(SUPPORTED_ACTIONS)}; or pass {{'code': '{{{{ ... }}}}'}} for anything else"
        )
    missing = [field for field in required if spec.get(field) is None]
    if missing:
        raise ValueError(
            f"set_widget_events: action {action!r} needs {', '.join(missing)}"
        )

    if action == "run_query":
        return f"{spec['query']}.run()"
    if action == "run_js":
        return f"{spec['object']}.{spec['function']}()"
    if action == "show_alert":
        style = spec.get("style")
        message = _q(spec["message"])
        return f"showAlert({message}, {_q(style)})" if style else f"showAlert({message})"
    if action == "show_modal":
        return f"showModal({_q(spec['modal'])})"
    if action == "close_modal":
        return f"closeModal({_q(spec['modal'])})"
    if action == "navigate_to":
        target = spec.get("page") or spec.get("url") or ""
        params = json.dumps(spec.get("params") or {})
        return f"navigateTo({_q(target)}, {params}, {_q(spec.get('target', 'SAME_WINDOW'))})"
    if action == "store_value":
        return f"storeValue({_q(spec['key'])}, {_q(spec['value'])})"
    if action == "clear_store":
        return "clearStore()"
    if action == "download":
        return f"download({spec['data']}, {_q(spec['name'])})"
    if action == "copy_to_clipboard":
        return f"copyToClipboard({_q(spec['text'])})"
    if action == "reset_widget":
        reset_children = "true" if spec.get("reset_children", True) else "false"
        return f"resetWidget({_q(spec['widget'])}, {reset_children})"
    if action == "set_interval":
        ms = int(spec.get("ms", 1000))
        return f"setInterval(() => {spec['callback']}, {ms}, {_q(spec.get('id', 'timer'))})"
    if action == "clear_interval":
        return f"clearInterval({_q(spec['id'])})"
    # post_message
    return (
        f"postWindowMessage({_q(spec['message'])}, {_q(spec.get('target', 'window'))}, "
        f"{_q(spec.get('origin', '*'))})"
    )


def build_action(spec: dict) -> tuple[str, bool]:
    """Return `(handler code, shows_as_native_dropdown)` for one event spec."""
    if "code" in spec:
        return spec["code"], False

    chain = _call(spec)
    success, failure = spec.get("on_success"), spec.get("on_failure")
    if not success and not failure:
        return "{{ " + chain + " }}", True

    if success:
        chain += f".then(() => {_call(success)})"
    if failure:
        chain += f".catch(() => {_call(failure)})"
    return "{{ " + chain + " }}", False
