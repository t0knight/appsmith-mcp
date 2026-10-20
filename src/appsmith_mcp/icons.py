"""Blueprint icon names (kebab-case) used by Appsmith's NATIVE icon-bearing widgets —
`ICON_WIDGET`, `ICON_BUTTON_WIDGET`, `BUTTON_WIDGET`, `MENU_BUTTON_WIDGET`, and table
`iconButton` columns. These come from `@blueprintjs/icons`, NOT the webfont (Tabler/Font
Awesome/etc.) you load inside a Custom Widget — so `"robot"` renders in a custom widget's
Tabler markup but is BLANK on a native ICON_WIDGET (feedback 3.7: an invalid iconName renders
nothing, with no error). Use this list to pick a real native icon, or fall back to a Custom
Widget when you need a glyph Blueprint doesn't have.

This is a curated, comprehensive subset of the stable Blueprint set — enough to cover UI needs.
The full catalog lives at https://blueprintjs.com/docs/#icons ."""

BLUEPRINT_ICON_NAMES = [
    # navigation / layout
    "home", "dashboard", "menu", "menu-open", "menu-closed", "more", "grid", "grid-view",
    "list", "list-detail-view", "layout", "layout-grid", "layout-auto", "panel-stats",
    "column-layout", "one-column", "two-columns", "three-columns", "page-layout",
    "maximize", "minimize", "fullscreen", "zoom-in", "zoom-out", "zoom-to-fit", "expand-all",
    "collapse-all", "drawer-left", "drawer-right", "panel-table",
    # arrows / direction
    "arrow-up", "arrow-down", "arrow-left", "arrow-right", "arrow-top-left", "arrow-top-right",
    "arrow-bottom-left", "arrow-bottom-right", "chevron-up", "chevron-down", "chevron-left",
    "chevron-right", "chevron-backward", "chevron-forward", "double-chevron-up",
    "double-chevron-down", "double-chevron-left", "double-chevron-right", "caret-up",
    "caret-down", "caret-left", "caret-right", "swap-horizontal", "swap-vertical", "refresh",
    "undo", "redo", "sort", "sort-asc", "sort-desc", "sort-alphabetical", "sort-numerical",
    # actions
    "add", "add-to-artifact", "insert", "remove", "delete", "trash", "edit", "annotation",
    "duplicate", "cut", "clipboard", "cross", "cross-circle", "tick", "tick-circle", "confirm",
    "small-tick", "small-cross", "plus", "minus", "ban-circle", "blocked-person", "floppy-disk",
    "download", "upload", "cloud-download", "cloud-upload", "import", "export", "share",
    "send-message", "send-to", "send-to-graph", "send-to-map", "link", "unlink", "paperclip",
    "pin", "unpin", "bookmark", "star", "star-empty", "heart", "heart-broken", "thumbs-up",
    "thumbs-down", "flag", "endorsed", "lock", "unlock", "key", "shield", "eye-open", "eye-off",
    "eye-on", "search", "search-around", "filter", "filter-list", "filter-open",
    "filter-remove", "settings", "cog", "wrench", "build", "power", "reset", "repeat",
    "automatic-updates", "history", "time", "stopwatch", "calendar", "clean",
    # status / feedback
    "info-sign", "warning-sign", "error", "help", "issue", "notifications", "notifications-updated",
    "feed", "map-marker", "geolocation", "locate", "path", "path-search", "predictive-analysis",
    # commerce / business
    "shopping-cart", "shop", "dollar", "euro", "bank-account", "credit-card", "briefcase",
    "book", "manual", "learning", "graduation-cap", "office", "barcode", "scan-code",
    "tag", "tags", "label", "box", "cube", "cubes", "delivery", "truck", "bring-data",
    "inbox", "outbox", "envelope", "paper", "id-number",
    # data / charts
    "chart", "timeline-bar-chart", "timeline-line-chart", "timeline-area-chart",
    "horizontal-bar-chart", "vertical-bar-chart", "grouped-bar-chart", "stacked-chart",
    "pie-chart", "doughnut-chart", "scatter-plot", "heat-grid", "trending-up", "trending-down",
    "comparison", "regression-chart", "data-lineage", "th", "th-list", "th-derived",
    "database", "th-filtered", "table", "join-table", "derive-column",
    "new-object", "diagram-tree", "flows", "graph", "layout-hierarchy", "sitemap",
    # media
    "media", "mobile-video", "video", "camera", "mobile-phone", "phone", "headset", "music",
    "volume-up", "volume-down", "volume-off", "mute", "play", "pause", "stop", "record",
    "fast-forward", "fast-backward", "step-forward", "step-backward", "image-rotate-left",
    "image-rotate-right", "picture-in-picture",
    # files / documents
    "document", "document-open", "document-share", "folder-close", "folder-open",
    "folder-new", "folder-shared", "add-to-folder", "projects", "print",
    "saved", "archive", "unarchive", "compressed", "code", "code-block", "console", "terminal",
    "application", "applications", "form", "properties", "variable", "function",
    # people / social
    "user", "people", "person", "new-person", "group-objects", "chat", "comment",
    "social-media", "globe", "globe-network", "ip-address", "map", "mail", "at",
    # misc
    "lightbulb", "flame", "flash", "moon", "snowflake", "cloud", "rain",
    "asterisk", "symbol-circle", "symbol-square", "symbol-triangle-up",
    "symbol-triangle-down", "symbol-diamond", "full-circle", "layers", "widget", "widget-button",
    "widget-footer", "widget-header", "control", "dot", "circle", "square", "selection",
    "multi-select", "segmented-control", "numbered-list", "manually-entered-data",
]
"""Stable set of Blueprint icon names (kebab-case)."""


def find_icon_names(query: str | None = None) -> list[str]:
    """Return Blueprint icon names, optionally filtered by a case-insensitive substring."""
    names = sorted(set(BLUEPRINT_ICON_NAMES))
    if not query:
        return names
    q = query.lower()
    return [n for n in names if q in n]
