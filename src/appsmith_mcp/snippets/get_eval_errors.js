(() => {
    // The editor's red evaluation errors live on the eval dataTree: each entity node carries
    // __evaluation__.errors, a map of property path -> array of error objects. Walk them all and
    // surface a concise list of what's broken (bindings / queries / JS) so the agent can debug.
    const tree = window.__store.getState().evaluations?.tree || {};
    const out = [];
    for (const [entity, node] of Object.entries(tree)) {
        if (!node || typeof node !== "object") continue;
        const errs = node.__evaluation__ && node.__evaluation__.errors;
        if (!errs || typeof errs !== "object") continue;
        const entityType = node.ENTITY_TYPE || null;
        const id = node.widgetId || node.actionId || node.collectionId || null;
        for (const [path, arr] of Object.entries(errs)) {
            if (!Array.isArray(arr)) continue;
            for (const e of arr) {
                // Keep the editor's red errors; skip lint/warnings.
                if (e && e.severity && e.severity !== "error") continue;
                const m = e && e.errorMessage;
                const message = m
                    ? (m.name ? `${m.name}: ${m.message}` : (m.message || String(m)))
                    : ((e && e.raw) || String(e));
                out.push({
                    entity,
                    entityType,
                    id,
                    property: path,
                    message,
                    errorType: (e && e.errorType) || null,
                    binding: e && e.originalBinding != null ? String(e.originalBinding).trim() : null,
                });
            }
        }
    }
    return { count: out.length, errors: out };
})()
