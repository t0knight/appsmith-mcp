(async () => {
    const store = window.__store;
    const cw = store.getState().entities.canvasWidgets || {};
    const out = [];
    const removedIds = [];
    for (const id of WIDGET_IDS) {
        const w = cw[id];
        if (!w) { out.push({ widgetId: id, error: "not found" }); continue; }
        // Dispatch keeps the live editor's client/eval state in sync (removes the widget from
        // the canvas + cleans up references); the explicit PUT below is what actually persists.
        store.dispatch({
            type: "WIDGET_DELETE",
            payload: { widgetId: id, parentId: w.parentId, disallowUndo: true },
        });
        removedIds.push(id);
        out.push({ widgetId: id });
    }
    if (removedIds.length) {
        // removedIds is passed explicitly so the widget is dropped from the persisted DSL
        // regardless of whether the WIDGET_DELETE saga has finished mutating the store yet.
        const p = await __persistLayout({ removedIds });
        for (const r of out) {
            if (r.error) continue;
            if (p.persisted) r.persisted = true;
            else r.error = p.error || ("save failed: HTTP " + p.status);
        }
    }
    return out;
})()
