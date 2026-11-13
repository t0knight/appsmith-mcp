(async () => {
    const store = window.__store;
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    const results = [];
    const actions = store.getState().entities.actions || [];

    // 1) Flip each target action's runBehaviour. ON_PAGE_LOAD forces it into the page's onLoad set;
    //    MANUAL removes it. (`executeOnLoad`/`userSetOnLoad` are legacy nulls in this Appsmith
    //    version — runBehaviour is the live field.)
    for (const id of ACTION_IDS) {
        const a = actions.find(x => x.config && x.config.id === id);
        if (!a) { results.push({ id, error: "query not found in the current app (is it on this page? switch_page first)" }); continue; }
        const merged = { ...a.config, runBehaviour: ENABLE ? "ON_PAGE_LOAD" : "MANUAL" };
        delete merged.eventData; delete merged.isValid;
        const r = await fetch(`/api/v1/actions/${id}`, {
            method: 'PUT', credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-XSRF-TOKEN': xsrf },
            body: JSON.stringify(merged),
        });
        const j = await r.json();
        if (!j.responseMeta?.success) { results.push({ id, error: j.responseMeta?.error?.message || 'update failed', status: r.status }); continue; }
        results.push({ id, name: j.data?.name, runBehaviour: j.data?.runBehaviour });
    }

    // Refresh Redux actions so a subsequent DSL rebuild sees the new runBehaviour.
    const appId = store.getState().ui.applications?.currentApplication?.id;
    const moduleId = store.getState().ui.editor?.currentModuleId;
    if (moduleId) store.dispatch({ type: "FETCH_MODULE_ENTITIES_INIT", payload: { moduleId } });
    else if (appId) store.dispatch({ type: "FETCH_ACTIONS_INIT", payload: { applicationId: appId } });

    // 2) Re-save the CURRENT page's layout. The updateLayout endpoint makes the server recompute
    //    layoutOnLoadActions from every action's runBehaviour (+ binding references) — which is the
    //    step update_queries(run_behaviour) alone was missing (feedback §5: an ON_PAGE_LOAD query
    //    never fired because layoutOnLoadActions was never regenerated).
    const p = await __persistLayout({});

    // 3) Read back the recomputed onLoad set from the page so the caller can confirm the query is
    //    now scheduled (server computes this synchronously as part of the layout save).
    let layoutOnLoadActions = null;
    try {
        const pid = store.getState().entities.pageList.currentPageId;
        // In a package module the on-load set lives on the module's layout.
        const rp = await fetch(moduleId ? `/api/v1/modules/${moduleId}` : `/api/v1/pages/${pid}`, { credentials: 'include', headers: { 'X-XSRF-TOKEN': xsrf } });
        const jp = await rp.json();
        const layout = jp.data?.layouts?.[0];
        layoutOnLoadActions = (layout?.layoutOnLoadActions || []).flat().map(x => ({ id: x.id, name: x.name }));
    } catch (e) {}

    return {
        results,
        layoutRecomputed: !!p.persisted,
        ...(p.persisted ? {} : { error: p.error || ("layout save failed: HTTP " + p.status) }),
        layoutOnLoadActions,
    };
})()
