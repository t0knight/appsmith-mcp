(() => {
    const state = window.__store.getState();
    const redacted = "[REDACTED]";
    const normalizeKey = key => String(key || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    const isSensitiveKey = key => {
        const normalized = normalizeKey(key);
        return normalized === "authorization"
            || normalized === "proxyauthorization"
            || normalized === "apikey"
            || normalized === "xapikey"
            || normalized === "password"
            || normalized === "clientsecret"
            || normalized === "servicerolekey"
            || normalized === "privatekey"
            || normalized.endsWith("token")
            || normalized.endsWith("password")
            || normalized.endsWith("secret");
    };
    const redact = (value, keyHint = "") => {
        if (isSensitiveKey(keyHint)) return redacted;
        if (Array.isArray(value)) return value.map(item => redact(item));
        if (value && typeof value === "object") {
            const isSensitiveHeader = typeof value.key === "string" && isSensitiveKey(value.key);
            const out = {};
            for (const [key, child] of Object.entries(value)) {
                out[key] = isSensitiveHeader && key === "value"
                    ? redacted
                    : redact(child, key);
            }
            return out;
        }
        return value;
    };

    if (MODE === "get_store") {
        const source = state.evaluations?.tree?.appsmith?.store || {};
        const keys = Array.isArray(ARG?.keys) && ARG.keys.length ? ARG.keys : Object.keys(source);
        const store = {};
        for (const key of keys) {
            if (Object.prototype.hasOwnProperty.call(source, key)) store[key] = redact(source[key], key);
        }
        return { store };
    }

    if (MODE === "eval_value") {
        const path = String(ARG?.path || "").trim();
        if (!path || !/^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[\d+\])*$/.test(path)) {
            return { path, found: false, error: "path must contain only property names and numeric indexes" };
        }
        const segments = path.replace(/\[(\d+)\]/g, ".$1").split(".");
        let value = state.evaluations?.tree || {};
        for (const segment of segments) {
            if (value == null || !Object.prototype.hasOwnProperty.call(Object(value), segment)) {
                return { path, found: false };
            }
            value = value[segment];
        }
        return { path, found: true, value: redact(value, segments[segments.length - 1]) };
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
        const environments = Object.entries(datasource.datasourceStorages || {}).map(([environmentId, storage]) => ({
            environmentId: storage?.environmentId || environmentId,
            datasourceConfiguration: redact(storage?.datasourceConfiguration || {}),
        }));
        return {
            id: datasource.id,
            name: datasource.name,
            pluginId: datasource.pluginId,
            workspaceId: datasource.workspaceId,
            environments,
        };
    }

    return { error: `unknown inspection mode ${MODE}` };
})()
