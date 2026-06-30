(async () => {
    const store = window.__store;
    const state = store.getState();
    const cw = state.entities.canvasWidgets || {};
    const pid = state.entities.pageList.currentPageId;
    const pw = (state.ui.pageWidgets || {})[pid];
    const appId = state.ui.applications?.currentApplication?.id;
    const layoutId = pw && pw.layoutId;

    const out = [];
    const overrides = {};

    for (const u of WIDGETS) {
        const w = cw[u.widget_id];
        if (!w) { out.push({ widget_id: u.widget_id, error: "widget not found" }); continue; }
        const merged = { ...(w.srcDoc || {}), ...(u.srcDoc || {}) };
        store.dispatch({
            type: "UPDATE_WIDGET_PROPERTY_REQUEST",
            payload: { widgetId: u.widget_id, propertyPath: "srcDoc", propertyValue: merged },
        });
        store.dispatch({
            type: "UPDATE_WIDGET_PROPERTY_REQUEST",
            payload: { widgetId: u.widget_id, propertyPath: "uncompiledSrcDoc", propertyValue: merged },
        });
        overrides[u.widget_id] = merged;
    }

    if (!appId || !layoutId || !pid) {
        for (const u of WIDGETS) {
            if (!out.find(r => r.widget_id === u.widget_id)) {
                out.push({ widget_id: u.widget_id, error: "missing applicationId/layoutId/pageId" });
            }
        }
        return out;
    }

    const build = (id) => {
        const src = cw[id];
        if (!src) return null;
        const node = { ...src };
        if (overrides[id]) {
            node.srcDoc = overrides[id];
            node.uncompiledSrcDoc = overrides[id];
        }
        if (Array.isArray(src.children)) {
            node.children = src.children.map(build).filter(x => x !== null);
        }
        return node;
    };
    const tree = build("0");
    if (!tree) {
        for (const u of WIDGETS) {
            if (!out.find(r => r.widget_id === u.widget_id)) {
                out.push({ widget_id: u.widget_id, error: "could not build DSL tree from canvasWidgets" });
            }
        }
        return out;
    }

    const url = "/api/v1/layouts/" + layoutId + "/pages/" + pid + "?applicationId=" + appId;
    let status = 0, errText = null;
    try {
        const r = await fetch(url, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ dsl: tree }),
        });
        status = r.status;
        if (!r.ok) {
            try { errText = (await r.text()).slice(0, 300); } catch (e) {}
        }
    } catch (e) {
        errText = String(e);
    }

    for (const u of WIDGETS) {
        if (out.find(r => r.widget_id === u.widget_id)) continue;
        if (status >= 200 && status < 300) {
            out.push({ widget_id: u.widget_id, synced: true });
        } else {
            out.push({ widget_id: u.widget_id, error: "save failed: HTTP " + status + (errText ? " " + errText : "") });
        }
    }
    return out;
})()
