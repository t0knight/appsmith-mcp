"""Small offline discovery payloads and allowlisted, packaged recipe sections."""

import re
from importlib import metadata, resources


_GUIDE_HEADINGS = {
    "download-binary": "1. Download a binary file produced by a webhook (n8n / any HTTP endpoint)",
    "external-api": "2. Consume a CORS-restricted external API → use a server-side REST query, not `fetch` in a custom widget",
    "custom-widget-model": "3. Custom-widget model values arrive as JSON strings",
    "page-load": "4. Run a query when the page opens",
    "table-actions": "5. Per-row button label/color in a table",
    "container-children": "6. Add a child to a modal/container/tabs",
    "icons": "7. Two icon universes",
    "query-auth": "8. Testing a session-token-authenticated query",
    "native-widgets": "Build like a person would (maintainability)",
    "packages": "Packages",
    "reading-state": "Reading state without large payloads",
    "diagnostics": "Diagnosing and verifying a saved change",
}


def build_capabilities(tool_names: list[str]) -> dict:
    try:
        version = metadata.version("appsmith-mcp")
    except metadata.PackageNotFoundError:
        version = "unknown"
    names = sorted(tool_names)
    return {
        "server": "appsmith-mcp", "version": version, "contractVersion": 1,
        "transport": "stdio", "toolCount": len(names), "tools": names,
        "policy": {
            "queryExecution": "read_only", "arbitraryJsExecution": False,
            "blockedTools": [name for name in ("run_command", "execute_js_functions") if name in names],
            "note": "SQL/JS authoring remains available; execution is separately restricted.",
        },
        "runtime": {
            "verified": False, "inspectWith": "get_build_context",
            "editorContexts": ["page", "package_module"],
            "note": "Static registration only; connection, Appsmith version and module availability are not checked.",
        },
        "guides": {"listWith": "get_guide", "count": len(_GUIDE_HEADINGS)},
    }


def read_guide(slug: str | None = None) -> dict:
    if slug is None:
        return {"ok": True, "guides": [
            {"slug": key, "title": title} for key, title in _GUIDE_HEADINGS.items()
        ]}
    heading = _GUIDE_HEADINGS.get(slug)
    if heading is None:
        return {"ok": False, "error": "unknown guide", "available": list(_GUIDE_HEADINGS)}

    # Input selects a registered heading, never a path. Reads also work from a wheel.
    markdown = resources.files("appsmith_mcp").joinpath("guides/recipes.md").read_text(encoding="utf-8")
    sections = list(re.finditer(r"(?m)^## (.+)$", markdown))
    for index, match in enumerate(sections):
        if match.group(1).strip() == heading:
            end = sections[index + 1].start() if index + 1 < len(sections) else len(markdown)
            return {"ok": True, "slug": slug, "title": heading,
                    "markdown": markdown[match.start():end].strip()}
    raise RuntimeError(f"bundled guide {slug!r} is missing its registered section")
