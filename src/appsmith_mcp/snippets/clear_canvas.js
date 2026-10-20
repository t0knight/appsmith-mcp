(async () => {
    const store = window.__store;
    const cw = store.getState().entities.canvasWidgets || {};
    const root = cw["0"];
    if (!root) return { error: "MainContainer not found" };
    const childIds = (root.children || []).slice();
    for (const id of childIds) {
        store.dispatch({
            type: "WIDGET_DELETE",
            payload: { widgetId: id, parentId: "0", disallowUndo: true },
        });
    }
    if (childIds.length) {
        const p = await __persistLayout({ removedIds: childIds });
        if (!p.persisted) {
            return { deleted: childIds.length, persisted: false, error: p.error || ("save failed: HTTP " + p.status) };
        }
    }
    return { deleted: childIds.length, persisted: true };
})()
