"""Reviewed MCP effect hints. These describe tools; execution policy enforces permissions."""

from mcp.types import ToolAnnotations


_READ = dict(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
_ADD = dict(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
_WRITE = dict(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
_RUNTIME = dict(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
_EXTERNAL_WRITE = {**_WRITE, "openWorldHint": True}

# Names are explicit, never inferred from prefixes. Unclassified additions fail registration.
# Replacement/configuration writes are conservative: they can overwrite existing values.
_CLASSES = (
    (_READ, """
        get_state_summary list_workspaces list_apps get_logs list_pages get_widget
        list_widgets list_children check_layout lint_design reset_widget_tree
        get_build_context get_eval_errors find_widgets get_widget_style get_page_background
        eval_value get_store list_plugins list_datasources get_datasource list_queries
        get_queries dump_state list_themes get_current_theme list_widget_types
        list_icon_names get_widget_schema list_js_objects get_js_objects get_custom_widget
        get_url screenshot get_render_health list_packages get_package list_module_instances
        get_capabilities get_guide
    """),
    (_ADD, """
        create_app add_widgets create_pages create_datasources create_queries save_custom_theme
        create_custom_widget create_js_objects create_package create_modules add_module_instances
    """),
    (_WRITE, """
        update_app delete_app update_widgets configure_table set_validation set_widget_events
        delete_widgets delete_pages set_widget_bounds rename_widgets reparent_widgets clear_canvas set_store
        update_queries set_page_load_actions set_run_behaviour delete_queries update_datasources
        delete_datasources set_theme delete_custom_themes update_theme manage_table_columns
        manage_tabs patch_js_objects patch_widget_code set_custom_widget_code sync_custom_widget
        update_custom_widget delete_custom_widget delete_js_objects update_js_objects import_page
        update_module publish_package update_module_instances delete_module_instances
        delete_packages delete_modules update_app_packages
    """),
    # Navigation/preview can run the app's own load/change actions. Do not promise a pure read.
    (_RUNTIME, "switch_page navigate refresh_page open_module preview_hidden execute_queries run_module_instances"),
    (_EXTERNAL_WRITE, "connect_widget_data export_page"),
    ({**_ADD}, "capture_screenshot"),  # optional scrolling; no persistent Appsmith edit
    (_READ, "execute_js_functions run_command"),  # always blocked, without touching the editor
)

_ANNOTATIONS = {}
for hints, names in _CLASSES:
    for name in names.split():
        if name in _ANNOTATIONS:
            raise ValueError(f"duplicate annotation classification: {name}")
        _ANNOTATIONS[name] = hints


def annotations_for(name: str) -> ToolAnnotations:
    try:
        hints = _ANNOTATIONS[name]
    except KeyError:
        raise ValueError(f"MCP tool {name!r} has no reviewed annotations") from None
    return ToolAnnotations(**hints)
