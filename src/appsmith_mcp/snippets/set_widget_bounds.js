(async () => {
    const store = window.__store;
    const out = [];
    const changed = [];
    for (const u of UPDATES) {
        const cw = store.getState().entities.canvasWidgets || {};
        const w = cw[u.widget_id];
        if (!w) { out.push({ widgetId: u.widget_id, error: "not found" }); continue; }
        const left = u.left != null ? u.left : w.leftColumn;
        const top = u.top != null ? u.top : w.topRow;
        const width = u.columns != null ? u.columns : w.rightColumn - w.leftColumn;
        const height = u.rows != null ? u.rows : w.bottomRow - w.topRow;
        let heightModeOverridden = null;
        if (u.rows != null && w.dynamicHeight && w.dynamicHeight !== "FIXED") {
            heightModeOverridden = w.dynamicHeight;
            store.dispatch({
                type: "BATCH_UPDATE_WIDGET_PROPERTY",
                payload: { widgetId: u.widget_id, updates: { modify: { dynamicHeight: "FIXED" } } },
            });
        }
        const requested = { leftColumn: left, topRow: top, rightColumn: left + width, bottomRow: top + height };
        store.dispatch({
            type: "WIDGET_RESIZE",
            payload: {
                widgetId: u.widget_id, parentId: w.parentId,
                leftColumn: left, topRow: top,
                rightColumn: left + width, bottomRow: top + height,
                snapColumnSpace: w.parentColumnSpace || 10,
                snapRowSpace: w.parentRowSpace || 10,
            },
        });
        // The store updates to the requested box synchronously, but the layout engine's
        // collision/reflow pass runs afterwards and can push the widget elsewhere. Reading
        // immediately echoed the request and hid that move (the widget landed a row lower and
        // nothing said so). Poll briefly for the box to stop changing, then report where it
        // actually ended up plus `moved` if that differs from what was asked.
        let v = store.getState().entities.canvasWidgets[u.widget_id];
        let prev = null;
        for (let i = 0; i < 8; i++) {
            const box = { leftColumn: v.leftColumn, topRow: v.topRow, rightColumn: v.rightColumn, bottomRow: v.bottomRow };
            if (prev && box.leftColumn === prev.leftColumn && box.topRow === prev.topRow
                && box.rightColumn === prev.rightColumn && box.bottomRow === prev.bottomRow) break;
            prev = box;
            await new Promise(r => setTimeout(r, 60));
            v = store.getState().entities.canvasWidgets[u.widget_id];
        }
        const effective = { leftColumn: v.leftColumn, topRow: v.topRow, rightColumn: v.rightColumn, bottomRow: v.bottomRow };
        const moved = effective.leftColumn !== requested.leftColumn || effective.topRow !== requested.topRow
            || effective.rightColumn !== requested.rightColumn || effective.bottomRow !== requested.bottomRow;
        const res = {
            widgetId: u.widget_id,
            leftColumn: effective.leftColumn, topRow: effective.topRow,
            rightColumn: effective.rightColumn, bottomRow: effective.bottomRow,
            requested,
            moved,
            heightModeOverridden,
        };
        out.push(res);
        changed.push(res);
    }
    // Persist once, after every box has settled, so the PUT captures the effective bounds.
    if (changed.length) {
        const p = await __persistLayout({});
        for (const r of changed) {
            if (p.persisted) r.persisted = true;
            else r.error = p.error || ("save failed: HTTP " + p.status);
        }
    }
    return out;
})()
