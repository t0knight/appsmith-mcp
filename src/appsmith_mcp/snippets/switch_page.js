(async () => {
    const store = window.__store;
    const pages = store.getState().entities.pageList?.pages || [];
    const p = pages.find(x => x.pageId === PAGE_ID);
    if (!p) return { error: `page ${PAGE_ID} not found` };

    const snap = () => {
        const s = store.getState();
        return {
            sel: s.entities.pageList.currentPageId,
            rend: s.ui.editor?.currentPageId,
            rootLoaded: !!s.entities.canvasWidgets?.["0"],
        };
    };

    // SWITCH_CURRENT_PAGE_ID alone only flips the SELECTED page id — it does NOT load/render
    // the target's DSL, leaving the canvas on the previous page (a divergence that would make
    // mutations corrupt the wrong page). FETCH_PAGE_INIT actually fetches + renders the page,
    // updating ui.editor.currentPageId and canvasWidgets. Dispatch both, then wait for both
    // the selected and rendered ids to settle on the target before returning.
    store.dispatch({ type: "SWITCH_CURRENT_PAGE_ID", payload: { id: PAGE_ID, slug: p.slug, permissions: p.userPermissions } });
    store.dispatch({ type: "FETCH_PAGE_INIT", payload: { id: PAGE_ID, pageId: PAGE_ID, isFirstLoad: false } });

    const start = Date.now();
    const done = () => { const x = snap(); return x.sel === PAGE_ID && x.rend === PAGE_ID && x.rootLoaded; };
    while (Date.now() - start < 10000 && !done()) {
        await new Promise(r => setTimeout(r, 150));
    }

    // Keep the browser URL in sync with the now-rendered page, so a later refresh_page reloads
    // THIS page instead of whatever the URL still pointed at (the round-1 footgun). This is a
    // replaceState — NOT a router navigate — so it only fixes the address bar; the Redux switch
    // above already rendered the page. Appsmith resolves the page from the id suffix regardless of
    // the slug part, and dropping any trailing /widgets/<id> just deselects (matches refresh_page).
    let urlUpdated = false;
    try {
        const appSlug = store.getState().ui.applications?.currentApplication?.slug;
        const seg = (p.slug ? p.slug + "-" : "") + (p.basePageId || PAGE_ID);
        if (appSlug && seg) {
            const newPath = `/app/${appSlug}/${seg}/edit`;
            if (location.pathname !== newPath) {
                history.replaceState(history.state, "", newPath + location.search + location.hash);
                urlUpdated = true;
            }
        }
    } catch (e) {}

    const x = snap();
    const consistent = x.sel === PAGE_ID && x.rend === PAGE_ID;
    return {
        pageId: PAGE_ID,
        switched: consistent,
        selectedPageId: x.sel,
        renderedPageId: x.rend,
        consistent,
        urlUpdated,
        url: location.href,
        ms: Date.now() - start,
        ...(consistent ? {} : { error: "page did not finish loading within timeout (selected/rendered still diverge)" }),
    };
})()
