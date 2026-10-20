(() => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    return IDS.map(id => {
        const w = cw[id];
        if (!w) return { widgetId: id, missing: true };
        // `keys` is the authoritative property list: it includes properties inherited from
        // base widgets that the dumped schema misses (e.g. `label` on INPUT_WIDGET_V2).
        const out = { widgetId: id, type: w.type, name: w.widgetName, keys: Object.keys(w) };
        // Handlers that are actually wired — a key can exist holding "" — so a caller can be
        // told when a setting it just turned on has no handler to drive it.
        out.handlers = Object.keys(w).filter(k => /^on[A-Z]/.test(k) && w[k]);
        // Column types let the caller be warned when a column event is wired to the wrong
        // handler for its type (e.g. onSubmit on a select column, which never fires).
        if (w.type === "TABLE_WIDGET_V2" && w.primaryColumns) {
            const columns = {};
            const editable = [];
            for (const [cid, col] of Object.entries(w.primaryColumns)) {
                if (!col || typeof col !== "object") continue;
                columns[cid] = col.columnType || "text";
                if (col.isEditable) editable.push(cid);
            }
            out.columns = columns;
            out.editableColumns = editable;
        }
        return out;
    });
})()
