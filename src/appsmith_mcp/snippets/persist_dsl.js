(async () => {
    // BATCH_UPDATE_WIDGET_PROPERTY (and the widget sagas) only mutate the client Redux
    // store and rely on a debounced autosave that often never lands. This PUT is what
    // makes a change survive a reload — the same call the editor makes when it saves the
    // layout. Callers may inject two optional constants:
    //   REMOVED_IDS: widget ids to prune (with all descendants) from the tree — needed for
    //                delete/clear, where WIDGET_DELETE is a saga and the store may not have
    //                dropped the node yet when this runs.
    //   OVERRIDES:   { widgetId: {prop: value, ...} } shallow-merged onto each node before
    //                serializing — for a mutation whose saga has not reflected in the store.
    const state = window.__store.getState();
    const cw = state.entities.canvasWidgets || {};
    const pid = state.entities.pageList.currentPageId;
    const pw = (state.ui.pageWidgets || {})[pid];
    const appId = state.ui.applications?.currentApplication?.id;
    const layoutId = pw && pw.layoutId;
    if (!appId || !layoutId || !pid) {
        return { saved: false, error: "could not resolve application/layout/page id" };
    }
    // Guard against the page-split corruption: SWITCH_CURRENT_PAGE_ID alone moves the
    // selected page (where this PUT lands) but leaves the previous page rendered (whose
    // widgets are in canvasWidgets). Persisting in that state writes the wrong page's tree
    // onto the selected page and silently destroys it. switch_page() dispatches
    // FETCH_PAGE_INIT so both converge — refuse until they do.
    const renderedPid = state.ui.editor && state.ui.editor.currentPageId;
    if (renderedPid && renderedPid !== pid) {
        return {
            saved: false,
            error: `page mismatch: page ${pid} is selected but ${renderedPid} is rendered — `
                 + `call switch_page("${pid}") first so the canvas matches the target`,
            selectedPageId: pid,
            renderedPageId: renderedPid,
        };
    }
    const removedIds = (typeof REMOVED_IDS !== 'undefined' && Array.isArray(REMOVED_IDS)) ? REMOVED_IDS : [];
    const overrides = (typeof OVERRIDES !== 'undefined' && OVERRIDES) ? OVERRIDES : {};
    // Expand removedIds with all descendants so a deleted subtree is fully pruned.
    const removed = new Set();
    const expand = (id) => {
        if (removed.has(id)) return;
        removed.add(id);
        const w = cw[id];
        if (w && Array.isArray(w.children)) w.children.forEach(expand);
    };
    removedIds.forEach(expand);
    const build = (id) => {
        if (removed.has(id)) return null;
        const src = cw[id];
        if (!src) return null;
        const node = { ...src, ...(overrides[id] || {}) };
        const kids = Array.isArray(node.children) ? node.children : null;
        if (kids) {
            node.children = kids.filter(c => !removed.has(c)).map(build).filter(x => x !== null);
        }
        return node;
    };
    const tree = build("0");
    if (!tree) return { saved: false, error: "canvas tree is empty" };
    try {
        const r = await fetch(`/api/v1/layouts/${layoutId}/pages/${pid}?applicationId=${appId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ dsl: tree }),
        });
        if (r.status >= 200 && r.status < 300) return { saved: true, pageId: pid };
        let detail = null;
        try { detail = (await r.text()).slice(0, 300); } catch (e) {}
        return { saved: false, error: `HTTP ${r.status}`, detail };
    } catch (e) {
        return { saved: false, error: String(e) };
    }
})()
