(async () => {
    // Copy a Custom Widget's source (and, by default, its defaultModel + events/trigger wiring)
    // onto one or more OTHER custom widgets — the "shared component" fan-out. A navbar replicated
    // as N identical custom widgets (one per page) is the canonical case: edit the source once,
    // then sync it to the rest instead of re-applying every patch N times.
    const store = window.__store;
    const cw = store.getState().entities.canvasWidgets || {};
    const src = cw[SOURCE_ID];
    if (!src) return { error: `source ${SOURCE_ID} not found` };
    if (src.type !== "CUSTOM_WIDGET") return { error: `source ${SOURCE_ID} is ${src.type}, not a CUSTOM_WIDGET` };

    const srcDoc = src.srcDoc || {};
    const uncompiled = src.uncompiledSrcDoc || srcDoc;
    // Top-level trigger handler prop names (event handlers live at the widget root, not nested).
    const triggerKeys = (src.dynamicTriggerPathList || []).map(p => p.key).filter(k => !k.includes("."));
    const isBinding = v => typeof v === "string" && /\{\{[\s\S]*?\}\}/.test(v);

    const results = [];
    const overrides = {};
    for (const tid of TARGET_IDS) {
        if (tid === SOURCE_ID) { results.push({ widget_id: tid, error: "target is the source" }); continue; }
        const t = cw[tid];
        if (!t) { results.push({ widget_id: tid, error: "target not found" }); continue; }
        if (t.type !== "CUSTOM_WIDGET") { results.push({ widget_id: tid, error: `target is ${t.type}, not a CUSTOM_WIDGET` }); continue; }

        const modify = { srcDoc, uncompiledSrcDoc: uncompiled };
        if (COPY_MODEL && src.defaultModel !== undefined) modify.defaultModel = src.defaultModel;
        if (COPY_EVENTS && src.events !== undefined) modify.events = src.events;
        if (COPY_EVENTS) for (const k of triggerKeys) if (k in src) modify[k] = src[k];

        // Recompute the target's dynamic path lists to include what we copied.
        let bindings = (t.dynamicBindingPathList || []).filter(p => p.key !== "defaultModel");
        if (isBinding(modify.defaultModel)) bindings = [...bindings, { key: "defaultModel" }];
        modify.dynamicBindingPathList = bindings;
        if (COPY_EVENTS) {
            const existing = (t.dynamicTriggerPathList || []).filter(p => !triggerKeys.includes(p.key));
            modify.dynamicTriggerPathList = [...existing, ...triggerKeys.map(key => ({ key }))];
        }

        // Refresh the editor's iframe with the new source (the srcDoc saga also updates the client
        // node), then keep the rest of the client node consistent by direct patch (unfrozen state,
        // no BATCH_UPDATE) so a later __persistLayout rebuild doesn't drop what we copied.
        store.dispatch({ type: "UPDATE_WIDGET_PROPERTY_REQUEST", payload: { widgetId: tid, propertyPath: "srcDoc", propertyValue: srcDoc } });
        store.dispatch({ type: "UPDATE_WIDGET_PROPERTY_REQUEST", payload: { widgetId: tid, propertyPath: "uncompiledSrcDoc", propertyValue: uncompiled } });
        const live = store.getState().entities.canvasWidgets[tid];
        if (live) for (const [k, v] of Object.entries(modify)) if (k !== "srcDoc" && k !== "uncompiledSrcDoc") live[k] = v;

        overrides[tid] = modify;
        results.push({ widget_id: tid, name: t.widgetName });
    }

    if (Object.keys(overrides).length) {
        const p = await __persistLayout({ overrides });
        for (const r of results) {
            if (r.error) continue;
            if (p.persisted) r.synced = true;
            else r.error = p.error || ("save failed: HTTP " + p.status);
        }
    }
    return { source: SOURCE_ID, targets: results };
})()
