(() => {
    // Grep the current page's widgets by type and/or property value, so callers stop hand-writing
    // a canvasWidgets scan in run_command. `WHERE` matches top-level props: value "*" means "set to
    // a non-empty value", anything else is an exact match. `TYPE` filters by widget type.
    const cw = window.__store.getState().entities.canvasWidgets || {};
    const where = WHERE || {};
    const wantType = TYPE || null;
    const parentId = PARENT_ID || null;
    // When filtering by parent, resolve a container/tabs/form/modal to its inner CANVAS_WIDGET so
    // callers can pass the container id directly (children actually live under the inner canvas).
    let parents = null;
    if (parentId) {
        parents = new Set([parentId]);
        for (const c of Object.values(cw)) if (c && c.parentId === parentId && c.type === "CANVAS_WIDGET") parents.add(c.widgetId);
    }
    const out = [];
    for (const w of Object.values(cw)) {
        if (!w || w.type === "CANVAS_WIDGET") continue;
        if (wantType && w.type !== wantType) continue;
        if (parents && !parents.has(w.parentId)) continue;
        let ok = true;
        const matched = {};
        for (const [k, v] of Object.entries(where)) {
            const wv = w[k];
            if (v === "*" || v === null) {
                if (wv === undefined || wv === null || wv === "") { ok = false; break; }
            } else if (wv !== v) { ok = false; break; }
            matched[k] = wv;
        }
        if (ok) out.push({ id: w.widgetId, name: w.widgetName, type: w.type, ...(Object.keys(matched).length ? { matched } : {}) });
    }
    return { count: out.length, widgets: out };
})()
