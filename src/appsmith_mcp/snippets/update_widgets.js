(async () => {
    const COMPOSITE = {
        STATBOX_WIDGET: { label: 0, value: 1, change: 2 },
    };
    // type -> its real label property ("label" for most, "labelText" for select/slider/group).
    // Injected from server.py; an empty map (unreplaced) just disables normalization.
    const LABEL_PROP_BY_TYPE = /*__LABEL_MAP__*/{};

    const store = window.__store;
    const overrides = {}; // widgetId -> property modifications to persist into the DSL

    const applyOne = (widgetId, props, triggerKeys) => {
        const cw = store.getState().entities.canvasWidgets || {};
        const w = cw[widgetId];
        if (!w) return { widgetId, error: `widget ${widgetId} not found` };

        const composite = COMPOSITE[w.type];
        const delegated = [];
        const remaining = { ...props };

        // Accept `label`/`labelText` interchangeably and normalize to whichever this widget type
        // actually uses, so a caller doesn't lose a round-trip discovering the right name.
        const normalized = [];
        const labelProp = LABEL_PROP_BY_TYPE[w.type];
        if (labelProp) {
            const other = labelProp === "label" ? "labelText" : "label";
            if (other in remaining && !(labelProp in remaining)) {
                remaining[labelProp] = remaining[other];
                delete remaining[other];
                normalized.push({ from: other, to: labelProp });
            }
        }
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

        // Final values + binding/trigger/JS-mode path lists, exactly as the property pane stores them.
        const policy = __propertyPolicy({ widget: w, props: remaining, triggerKeys: triggerKeys || [] });
        const registered = { ...policy.registered, delegated, normalized };

        if (Object.keys(remaining).length || (composite && delegated.length === 0)) {
            const modify = policy.modify;
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

    const results = UPDATES.map(u => applyOne(u.widget_id, u.props || {}, u.trigger_keys || []));

    // Persist via the shared explicit layout PUT — BATCH_UPDATE_WIDGET_PROPERTY only mutates the
    // client Redux store and relies on a debounced autosave that often never lands. `overrides`
    // carries the modified props (incl. delegated composite children) into the DSL tree.
    if (Object.keys(overrides).length) {
        const p = await __persistLayout({ overrides });
        for (const res of results) {
            if (res.error || !overrides[res.widgetId]) continue;
            if (p.persisted) res.persisted = true;
            else res.error = p.error || ("save failed: HTTP " + p.status);
        }
    }

    return results;
})()
