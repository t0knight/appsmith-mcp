(() => {
    // Fixed, read-only inspections of the editor state. Nothing caller-provided is evaluated
    // as code. Values are returned as stored; the server masks secrets before they reach the
    // agent (see redaction.py).
    const state = window.__store.getState();

    if (MODE === "get_store") {
        const source = state.evaluations?.tree?.appsmith?.store || {};
        const keys = Array.isArray(ARG?.keys) && ARG.keys.length ? ARG.keys : Object.keys(source);
        const store = {};
        for (const key of keys) {
            if (Object.prototype.hasOwnProperty.call(source, key)) store[key] = source[key];
        }
        return { store };
    }

    if (MODE === "eval_value") {
        const pathRe = /^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[\d+\])*$/;
        return (ARG?.paths || []).map(raw => {
            const path = String(raw || "").trim();
            if (!pathRe.test(path)) {
                return { path, found: false, error: "path must contain only property names and numeric indexes" };
            }
            let value = state.evaluations?.tree || {};
            for (const segment of path.replace(/\[(\d+)\]/g, ".$1").split(".")) {
                if (value == null || !Object.prototype.hasOwnProperty.call(Object(value), segment)) {
                    return { path, found: false };
                }
                value = value[segment];
            }
            return { path, found: true, value };
        });
    }

    if (MODE === "list_children") {
        const widgets = state.entities?.canvasWidgets || {};
        const requested = String(ARG?.parent_id || "");
        const parent = widgets[requested]
            || Object.values(widgets).find(widget => widget?.widgetName === requested);
        if (!parent) return { error: `parent ${requested} not found` };
        return Object.values(widgets)
            .filter(widget => widget && widget.parentId === parent.widgetId)
            .map(widget => ({
                id: widget.widgetId,
                name: widget.widgetName,
                type: widget.type,
                parentId: widget.parentId,
                leftColumn: widget.leftColumn,
                topRow: widget.topRow,
                rightColumn: widget.rightColumn,
                bottomRow: widget.bottomRow,
                isVisible: widget.isVisible !== false,
            }))
            .sort((a, b) => ((a.topRow || 0) - (b.topRow || 0)) || ((a.leftColumn || 0) - (b.leftColumn || 0)));
    }

    if (MODE === "get_datasource") {
        const requested = String(ARG?.datasource_id || "");
        const datasource = (state.entities?.datasources?.list || []).find(
            item => item?.id === requested || item?.name === requested
        );
        if (!datasource) return { error: `datasource ${requested} not found` };
        return {
            id: datasource.id,
            name: datasource.name,
            pluginId: datasource.pluginId,
            workspaceId: datasource.workspaceId,
            environments: Object.entries(datasource.datasourceStorages || {}).map(([environmentId, storage]) => ({
                environmentId: storage?.environmentId || environmentId,
                datasourceConfiguration: storage?.datasourceConfiguration || {},
            })),
        };
    }

    return { error: `unknown inspection mode ${MODE}` };
})()
