(() => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    const out = [];
    for (const id of WIDGET_IDS) {
        const w = cw[id];
        if (!w) { out.push({ widgetId: id, error: "not found" }); continue; }
        window.__store.dispatch({
            type: "WIDGET_DELETE",
            payload: { widgetId: id, parentId: w.parentId, disallowUndo: true },
        });
        out.push({ widgetId: id, deleted: true });
    }
    return out;
})()
