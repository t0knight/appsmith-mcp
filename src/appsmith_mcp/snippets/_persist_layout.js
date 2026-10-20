// Shared layout-persistence helper (WS1). Raw JS *expression* — an async function —
// injected into a snippet's outer scope via run_snippet(js_helpers={...}); the snippet's
// IIFE closes over it and can `await __persistLayout({overrides, removedIds})`.
//
// Page editor: rebuilds the page DSL tree from the live `canvasWidgets` (root "0"), applies
// per-widget `overrides`, drops `removedIds` (and their descendants), then does an explicit
// PUT /api/v1/layouts/{layoutId}/pages/{pageId}. This is the ONLY honest persistence path there:
// dispatching to Redux alone relies on a debounced autosave that "often never lands".
//
// Package module editor: the editor saves the module layout itself (~1s after any canvas change)
// and re-initialises the canvas from that save, so a direct PUT gets overwritten. There the final
// widgets go to the editor (UPDATE_LAYOUT) and we wait until its module save lands.
//
// Returns { persisted:true, ... } once saved, else { persisted:false, status?, error }.
async ({ overrides = {}, removedIds = [] } = {}) => {
    const store = window.__store;
    const state = store.getState();
    const cw = state.entities.canvasWidgets || {};
    const moduleId = state.ui.editor?.currentModuleId;
    const module = moduleId && (state.entities.modules || {})[moduleId];
    const pid = state.entities.pageList.currentPageId;
    const pw = (state.ui.pageWidgets || {})[pid];
    const appId = state.ui.applications?.currentApplication?.id;
    const layoutId = pw && pw.layoutId;
    if (!module && (!appId || !layoutId || !pid)) {
        return { persisted: false, error: "missing applicationId/layoutId/pageId" };
    }
    // Refuse to write when the rendered canvas (ui.editor.currentPageId, whose widgets ARE
    // canvasWidgets) diverges from the selected page (pageList.currentPageId, the PUT target):
    // building the rendered tree and PUTting it to the selected page's layout would overwrite
    // the OTHER page. This happens when the caller flips pages without a real page load — the
    // fix is to switch_page (which fetches/renders the target) before mutating.
    const rendered = state.ui.editor?.currentPageId;
    if (!module && rendered && rendered !== pid) {
        return { persisted: false, error: "page context inconsistent: canvas renders " + rendered + " but selected page is " + pid + " — call switch_page(" + pid + ") before mutating" };
    }

    // Expand the removed set to include every descendant so no orphan nodes linger in the DSL.
    const removed = new Set(removedIds || []);
    const expand = (id) => {
        const w = cw[id];
        if (!w) return;
        for (const c of (w.children || [])) { if (!removed.has(c)) { removed.add(c); expand(c); } }
    };
    for (const id of [...removed]) expand(id);

    if (module) {
        const widgets = {};
        for (const [id, w] of Object.entries(cw)) {
            if (removed.has(id)) continue;
            const node = { ...w, ...(overrides[id] || {}) };
            if (Array.isArray(node.children)) node.children = node.children.filter(cid => !removed.has(cid));
            widgets[id] = node;
        }
        const before = (state.entities.modules || {})[moduleId];
        const find = (n, id) => (!n ? null : n.widgetId === id ? n : (n.children || []).map(c => find(c, id)).find(Boolean) || null);
        const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
        // Compare plain values only: the editor may legitimately reshape objects on save (a table
        // recalculates its columns from the data, for instance).
        const plain = v => v === null || ["string", "number", "boolean"].includes(typeof v);
        const landed = dsl => Object.entries(overrides).every(([id, props]) => {
            const n = find(dsl, id);
            return n && Object.entries(props).every(([k, v]) => !plain(v) || same(n[k], v));
        }) && [...removed].every(id => !find(dsl, id));
        store.dispatch({ type: "UPDATE_LAYOUT", payload: { widgets } });
        const start = Date.now();
        while (Date.now() - start < 12000) {
            const m = (store.getState().entities.modules || {})[moduleId];
            const dsl = m && m.layouts && m.layouts[0] && m.layouts[0].dsl;
            if (m !== before && dsl && landed(dsl)) return { persisted: true, moduleId, via: "module editor" };
            await new Promise(r => setTimeout(r, 200));
        }
        return { persisted: false, error: "the module editor did not confirm the layout save within 12s — check get_logs and retry" };
    }

    const build = (id) => {
        const src = cw[id];
        if (!src) return null;
        // Override wins over the stored node; an override may itself supply a new `children` array
        // (e.g. reparent), so read children off the merged node, then filter out removed ids.
        const node = { ...src, ...(overrides[id] || {}) };
        const kids = Array.isArray(node.children) ? node.children : null;
        if (kids) {
            node.children = kids.filter(cid => !removed.has(cid)).map(build).filter(x => x !== null);
        }
        return node;
    };
    const tree = build("0");
    if (!tree) return { persisted: false, error: "could not build DSL tree from canvasWidgets" };

    const url = "/api/v1/layouts/" + layoutId + "/pages/" + pid + "?applicationId=" + appId;
    try {
        const r = await fetch(url, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ dsl: tree }),
        });
        const ok = r.status >= 200 && r.status < 300;
        if (ok) return { persisted: true, status: r.status, pageId: pid };
        let errText = null;
        try { errText = (await r.text()).slice(0, 300); } catch (e) {}
        return { persisted: false, status: r.status, error: "save failed: HTTP " + r.status + (errText ? " " + errText : "") };
    } catch (e) {
        return { persisted: false, error: String(e) };
    }
}
