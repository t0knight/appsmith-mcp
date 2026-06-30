(() => {
    const out = [];
    for (const u of UPDATES) {
        const cw = window.__store.getState().entities.canvasWidgets || {};
        const w = cw[u.widget_id];
        if (!w) { out.push({ widgetId: u.widget_id, error: "not found" }); continue; }
        const oldParent = cw[w.parentId];
        const newParent = cw[u.new_parent_id];
        if (!newParent) { out.push({ widgetId: u.widget_id, error: `parent ${u.new_parent_id} not found` }); continue; }
        if (newParent.type !== "CANVAS_WIDGET" && !newParent.children) {
            out.push({ widgetId: u.widget_id, error: `parent ${u.new_parent_id} (${newParent.type}) doesn't accept children` });
            continue;
        }
        if (w.parentId === u.new_parent_id) {
            out.push({ widgetId: u.widget_id, parent: u.new_parent_id, unchanged: true });
            continue;
        }
        const oldChildren = (oldParent.children || []).filter(id => id !== u.widget_id);
        const newChildren = [...(newParent.children || []), u.widget_id];
        window.__store.dispatch({
            type: "BATCH_UPDATE_WIDGET_PROPERTY",
            payload: { widgetId: w.parentId, updates: { modify: { children: oldChildren } } },
        });
        window.__store.dispatch({
            type: "BATCH_UPDATE_WIDGET_PROPERTY",
            payload: { widgetId: u.new_parent_id, updates: { modify: { children: newChildren } } },
        });
        window.__store.dispatch({
            type: "BATCH_UPDATE_WIDGET_PROPERTY",
            payload: { widgetId: u.widget_id, updates: { modify: { parentId: u.new_parent_id } } },
        });
        out.push({ widgetId: u.widget_id, oldParent: w.parentId, newParent: u.new_parent_id });
    }
    return out;
})()
