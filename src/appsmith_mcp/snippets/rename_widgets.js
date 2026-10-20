(async () => {
    const store = window.__store;
    const out = [];
    const pending = [];
    for (const u of UPDATES) {
        const cw = store.getState().entities.canvasWidgets || {};
        if (!cw[u.widget_id]) { out.push({ widgetId: u.widget_id, error: "not found" }); continue; }
        // UPDATE_WIDGET_NAME_INIT is a saga: it validates uniqueness and rewrites references,
        // and does NOT update widgetName synchronously. Dispatch now, poll below, then PUT.
        store.dispatch({
            type: "UPDATE_WIDGET_NAME_INIT",
            payload: { id: u.widget_id, newName: u.new_name },
        });
        const res = { widgetId: u.widget_id, requestedName: u.new_name };
        out.push(res);
        pending.push(res);
    }
    // Wait for each rename to land (or reject) before persisting, so the PUT captures the new
    // name rather than the old one. A name that never applies means Appsmith rejected it.
    if (pending.length) {
        const start = Date.now();
        const settled = () => pending.every(r => {
            const w = store.getState().entities.canvasWidgets[r.widgetId];
            return w && w.widgetName === r.requestedName;
        });
        while (Date.now() - start < 4000 && !settled()) {
            await new Promise(r => setTimeout(r, 100));
        }
        const anyApplied = pending.some(r => {
            const w = store.getState().entities.canvasWidgets[r.widgetId];
            return w && w.widgetName === r.requestedName;
        });
        for (const r of pending) {
            const w = store.getState().entities.canvasWidgets[r.widgetId];
            r.appliedName = w ? w.widgetName : null;
            if (!w || w.widgetName !== r.requestedName) {
                r.error = "rename not applied (name may conflict or be invalid)";
            }
        }
        if (anyApplied) {
            const p = await __persistLayout({});
            for (const r of pending) {
                if (r.error) continue;
                if (p.persisted) r.persisted = true;
                else r.error = p.error || ("save failed: HTTP " + p.status);
            }
        }
    }
    return out;
})()
