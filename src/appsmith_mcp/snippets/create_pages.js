(async () => {
    const store = window.__store;
    const s = store.getState();
    const applicationId = s.ui.applications?.currentApplication?.id;
    if (!applicationId) return { error: "no current application — open an app editor first" };

    const pageId = p => p.pageId || p.id;
    const pageName = p => p.pageName || p.name;
    const before = new Set((store.getState().entities.pageList?.pages || []).map(pageId));

    for (const name of NAMES) {
        store.dispatch({
            type: "CREATE_PAGE_INIT",
            payload: {
                applicationId, name,
                layouts: [{ dsl: { widgetName: "MainContainer", type: "CANVAS_WIDGET", widgetId: "0", children: [], leftColumn: 0, rightColumn: 0, topRow: 0, bottomRow: 0, version: 94 } }],
            },
        });
    }

    // CREATE_PAGE_INIT is a saga that round-trips to the backend to mint the real pageId;
    // poll pageList until the new pages land so the caller gets usable ids immediately.
    const wanted = new Set(NAMES);
    const found = {};
    const start = Date.now();
    while (Date.now() - start < 8000 && Object.keys(found).length < NAMES.length) {
        for (const p of (store.getState().entities.pageList?.pages || [])) {
            if (!before.has(pageId(p)) && wanted.has(pageName(p)) && !found[pageName(p)]) {
                found[pageName(p)] = pageId(p);
            }
        }
        if (Object.keys(found).length >= NAMES.length) break;
        await new Promise(r => setTimeout(r, 200));
    }

    return NAMES.map(name => ({ dispatched: true, name, applicationId, pageId: found[name] || null }));
})()
