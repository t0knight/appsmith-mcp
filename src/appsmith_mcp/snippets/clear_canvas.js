(() => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    const root = cw["0"];
    if (!root) return { error: "MainContainer not found" };
    const childIds = (root.children || []).slice();
    for (const id of childIds) {
        window.__store.dispatch({
            type: "WIDGET_DELETE",
            payload: { widgetId: id, parentId: "0", disallowUndo: true },
        });
    }
    return { deleted: childIds.length };
})()
