(async () => {
    const COMPOSITE = {
        STATBOX_WIDGET: { label: 0, value: 1, change: 2 },
    };
    const bindRe = /\{\{[\s\S]*?\}\}/;
    const isBindingValue = v => typeof v === "string" && bindRe.test(v);
    const isTriggerName = k => k.startsWith("on");
    const isPlainObject = x => x && typeof x === "object" && !Array.isArray(x);
    const deepMerge = (target, source) => {
        if (!isPlainObject(target) || !isPlainObject(source)) return source;
        const out = { ...target };
        for (const [k, v] of Object.entries(source)) {
            out[k] = isPlainObject(v) && isPlainObject(out[k]) ? deepMerge(out[k], v) : v;
        }
        return out;
    };

    const store = window.__store;
    const overrides = {}; // widgetId -> property modifications to persist into the DSL

    const applyOne = (widgetId, props) => {
        const cw = store.getState().entities.canvasWidgets || {};
        const w = cw[widgetId];
        if (!w) return { widgetId, error: `widget ${widgetId} not found` };

        const composite = COMPOSITE[w.type];
        const delegated = [];
        const remaining = { ...props };
        if (composite) {
            const canvas = Object.values(cw).find(c => c.parentId === w.widgetId && c.type === "CANVAS_WIDGET");
            const textKids = Object.values(cw)
                .filter(c => c.parentId === canvas?.widgetId && c.type === "TEXT_WIDGET")
                .sort((a, b) => a.topRow - b.topRow);
            for (const [k, idx] of Object.entries(composite)) {
                if (k in remaining && textKids[idx]) {
                    const childId = textKids[idx].widgetId;
                    store.dispatch({
                        type: "BATCH_UPDATE_WIDGET_PROPERTY",
                        payload: { widgetId: childId, updates: { modify: { text: remaining[k] } } },
                    });
                    overrides[childId] = { ...(overrides[childId] || {}), text: remaining[k] };
                    delegated.push({ key: k, childWidgetId: childId });
                    delete remaining[k];
                }
            }
        }

        if (w.type === "MODAL_WIDGET" && "isVisible" in remaining) {
            // Show/hide is a runtime action, not a persisted property.
            if (remaining.isVisible) {
                store.dispatch({ type: "SHOW_MODAL", payload: { modalId: w.widgetId } });
            } else {
                store.dispatch({ type: "CLOSE_MODAL", payload: { modalName: w.widgetName } });
            }
            delegated.push({ key: "isVisible", action: remaining.isVisible ? "SHOW_MODAL" : "CLOSE_MODAL" });
            delete remaining.isVisible;
        }

        const touched = Object.keys(remaining);
        const bindList = (w.dynamicBindingPathList || []).filter(p => !touched.includes(p.key));
        const triggerList = (w.dynamicTriggerPathList || []).filter(p => !touched.includes(p.key));

        const registered = { bindings: [], triggers: [], literals: [], delegated };
        for (const [k, v] of Object.entries(remaining)) {
            if (isTriggerName(k)) {
                triggerList.push({ key: k });
                registered.triggers.push(k);
            } else if (isBindingValue(v)) {
                bindList.push({ key: k });
                registered.bindings.push(k);
            } else {
                registered.literals.push(k);
            }
        }

        const merged = {};
        for (const [k, v] of Object.entries(remaining)) {
            merged[k] = isPlainObject(v) && isPlainObject(w[k]) ? deepMerge(w[k], v) : v;
        }

        if (Object.keys(remaining).length || (composite && delegated.length === 0)) {
            const modify = {
                ...merged,
                dynamicBindingPathList: bindList,
                dynamicTriggerPathList: triggerList,
            };
            // BATCH_UPDATE keeps the live client/eval state in sync; the DSL-PUT below is
            // what actually persists server-side.
            store.dispatch({
                type: "BATCH_UPDATE_WIDGET_PROPERTY",
                payload: { widgetId, updates: { modify } },
            });
            overrides[widgetId] = { ...(overrides[widgetId] || {}), ...modify };
        }

        return { widgetId, name: w.widgetName, applied: registered };
    };

    const results = UPDATES.map(u => applyOne(u.widget_id, u.props || {}));

    // Persist via an explicit layout PUT — BATCH_UPDATE_WIDGET_PROPERTY only mutates the
    // client Redux store and relies on a debounced autosave that often never lands.
    if (Object.keys(overrides).length) {
        const state = store.getState();
        const cw = state.entities.canvasWidgets || {};
        const pid = state.entities.pageList.currentPageId;
        const pw = (state.ui.pageWidgets || {})[pid];
        const appId = state.ui.applications?.currentApplication?.id;
        const layoutId = pw && pw.layoutId;
        if (appId && layoutId && pid) {
            const build = (id) => {
                const src = cw[id];
                if (!src) return null;
                const node = { ...src, ...(overrides[id] || {}) };
                if (Array.isArray(src.children)) {
                    node.children = src.children.map(build).filter(x => x !== null);
                }
                return node;
            };
            const tree = build("0");
            if (tree) {
                const url = "/api/v1/layouts/" + layoutId + "/pages/" + pid + "?applicationId=" + appId;
                try {
                    const r = await fetch(url, {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        credentials: "include",
                        body: JSON.stringify({ dsl: tree }),
                    });
                    const ok = r.status >= 200 && r.status < 300;
                    let errText = null;
                    if (!ok) { try { errText = (await r.text()).slice(0, 300); } catch (e) {} }
                    for (const res of results) {
                        if (!res.error && overrides[res.widgetId]) {
                            if (ok) res.synced = true;
                            else res.error = "save failed: HTTP " + r.status + (errText ? " " + errText : "");
                        }
                    }
                } catch (e) {
                    for (const res of results) {
                        if (!res.error && overrides[res.widgetId]) res.error = String(e);
                    }
                }
            }
        }
    }

    return results;
})()
