(async () => {
    const store = window.__store;
    const cw = store.getState().entities.canvasWidgets || {};
    const out = [];
    const overrides = {};

    for (const u of WIDGETS) {
        const w = cw[u.widget_id];
        if (!w) { out.push({ widget_id: u.widget_id, error: "widget not found on the current page. Only the loaded page is reachable — switch_page to the page that owns this widget and retry." }); continue; }
        // Guard set_custom_widget_code (which passes a real srcDoc) against a wrong widget type —
        // the internal flush callers pass no srcDoc and are unaffected.
        if (u.srcDoc && Object.keys(u.srcDoc).length && w.type !== "CUSTOM_WIDGET") {
            out.push({ widget_id: u.widget_id, error: `widget is ${w.type}, not a CUSTOM_WIDGET` });
            continue;
        }
        const merged = { ...(w.srcDoc || {}), ...(u.srcDoc || {}) };
        store.dispatch({
            type: "UPDATE_WIDGET_PROPERTY_REQUEST",
            payload: { widgetId: u.widget_id, propertyPath: "srcDoc", propertyValue: merged },
        });
        store.dispatch({
            type: "UPDATE_WIDGET_PROPERTY_REQUEST",
            payload: { widgetId: u.widget_id, propertyPath: "uncompiledSrcDoc", propertyValue: merged },
        });
        // The DSL node carries srcDoc + uncompiledSrcDoc so a reload can't revert to the compiled-
        // only version; both go through the override into the shared layout PUT.
        overrides[u.widget_id] = { srcDoc: merged, uncompiledSrcDoc: merged };
        out.push({ widget_id: u.widget_id });
    }

    if (Object.keys(overrides).length) {
        const p = await __persistLayout({ overrides });
        for (const r of out) {
            if (r.error) continue;
            if (p.persisted) r.synced = true;
            else r.error = p.error || ("save failed: HTTP " + p.status);
        }
    }
    return out;
})()
