(() => {
    const out = [];
    for (const u of UPDATES) {
        const cw = window.__store.getState().entities.canvasWidgets || {};
        const w = cw[u.widget_id];
        if (!w) { out.push({ widgetId: u.widget_id, error: "not found" }); continue; }
        const left = u.left != null ? u.left : w.leftColumn;
        const top = u.top != null ? u.top : w.topRow;
        const width = u.columns != null ? u.columns : w.rightColumn - w.leftColumn;
        const height = u.rows != null ? u.rows : w.bottomRow - w.topRow;
        let heightModeOverridden = null;
        if (u.rows != null && w.dynamicHeight && w.dynamicHeight !== "FIXED") {
            heightModeOverridden = w.dynamicHeight;
            window.__store.dispatch({
                type: "BATCH_UPDATE_WIDGET_PROPERTY",
                payload: { widgetId: u.widget_id, updates: { modify: { dynamicHeight: "FIXED" } } },
            });
        }
        window.__store.dispatch({
            type: "WIDGET_RESIZE",
            payload: {
                widgetId: u.widget_id, parentId: w.parentId,
                leftColumn: left, topRow: top,
                rightColumn: left + width, bottomRow: top + height,
                snapColumnSpace: w.parentColumnSpace || 10,
                snapRowSpace: w.parentRowSpace || 10,
            },
        });
        const v = window.__store.getState().entities.canvasWidgets[u.widget_id];
        out.push({ widgetId: u.widget_id, leftColumn: v.leftColumn, topRow: v.topRow, rightColumn: v.rightColumn, bottomRow: v.bottomRow, heightModeOverridden });
    }
    return out;
})()
