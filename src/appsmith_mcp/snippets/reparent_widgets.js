(async () => {
    const store = window.__store;
    const out = [];
    let anyChanged = false;
    for (const u of UPDATES) {
        const cw = store.getState().entities.canvasWidgets || {};
        const w = cw[u.widget_id];
        if (!w) { out.push({ widgetId: u.widget_id, error: "not found" }); continue; }

        // Resolve the real drop target: containers/tabs/forms wrap an inner CANVAS_WIDGET,
        // and a widget must be parented to that canvas rather than the outer widget id.
        // (For a TABS_WIDGET this picks the first tab's canvas; pass a specific tab's
        // canvas id directly to target another tab.)
        let targetId = u.new_parent_id;
        let newParent = cw[targetId];
        if (!newParent) { out.push({ widgetId: u.widget_id, error: `parent ${u.new_parent_id} not found` }); continue; }
        let redirectedTo = null;
        if (newParent.type !== "CANVAS_WIDGET") {
            const innerCanvas = Object.values(cw).find(c => c.parentId === newParent.widgetId && c.type === "CANVAS_WIDGET");
            if (innerCanvas) { targetId = innerCanvas.widgetId; newParent = innerCanvas; redirectedTo = targetId; }
        }
        if (newParent.type !== "CANVAS_WIDGET") {
            out.push({ widgetId: u.widget_id, error: `parent ${u.new_parent_id} (${cw[u.new_parent_id].type}) doesn't accept children` });
            continue;
        }
        if (w.parentId === targetId) {
            out.push({ widgetId: u.widget_id, parent: targetId, unchanged: true });
            continue;
        }
        const oldParent = cw[w.parentId];
        const oldChildren = ((oldParent && oldParent.children) || []).filter(id => id !== u.widget_id);
        const newChildren = [...(newParent.children || []), u.widget_id];
        // These BATCH_UPDATEs are synchronous reducer writes, so canvasWidgets reflects the new
        // parentage immediately and the PUT below persists it.
        store.dispatch({
            type: "BATCH_UPDATE_WIDGET_PROPERTY",
            payload: { widgetId: w.parentId, updates: { modify: { children: oldChildren } } },
        });
        store.dispatch({
            type: "BATCH_UPDATE_WIDGET_PROPERTY",
            payload: { widgetId: targetId, updates: { modify: { children: newChildren } } },
        });
        store.dispatch({
            type: "BATCH_UPDATE_WIDGET_PROPERTY",
            payload: { widgetId: u.widget_id, updates: { modify: { parentId: targetId } } },
        });
        anyChanged = true;
        const res = { widgetId: u.widget_id, oldParent: w.parentId, newParent: targetId };
        if (redirectedTo) res.redirectedToInnerCanvas = redirectedTo;
        out.push(res);
    }
    if (anyChanged) {
        const p = await __persistLayout({});
        for (const r of out) {
            if (r.error || r.unchanged) continue;
            if (p.persisted) r.persisted = true;
            else r.error = p.error || ("save failed: HTTP " + p.status);
        }
    }
    return out;
})()
