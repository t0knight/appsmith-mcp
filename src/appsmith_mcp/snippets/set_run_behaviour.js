(async () => {
    // Set Manual / Automatic / On page load (/ On page unload) on queries and JS functions through the
    // same endpoint the editor's "Run behaviour" dropdown uses. The server recomputes the page's (or
    // module's) on-load set itself. AUTOMATIC re-runs on every dependency change (and on load), so it
    // is only accepted with an explicit `reason`.
    const ALLOWED = ["MANUAL", "ON_PAGE_LOAD", "AUTOMATIC", "ON_PAGE_UNLOAD"];
    const store = window.__store;
    const state = store.getState();
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    const actions = state.entities.actions || [];
    const collections = state.entities.jsActions || [];
    const moduleId = state.ui.editor?.currentModuleId;
    const pageId = state.entities.pageList?.currentPageId;

    const resolve = item => {
        if (item.query) {
            const a = actions.find(x => x.config && (x.config.id === item.query || x.config.name === item.query));
            return a ? { id: a.config.id, target: a.config.name, live: a.config } : { error: `query ${item.query} not found in this ${moduleId ? "module" : "page"}` };
        }
        if (item.js_object) {
            const c = collections.find(x => x.config && (x.config.id === item.js_object || x.config.name === item.js_object));
            if (!c) return { error: `JS object ${item.js_object} not found in this ${moduleId ? "module" : "page"}` };
            const f = (c.config.actions || []).find(x => x.name === item.function || x.id === item.function);
            if (!f) return { error: `function ${item.function} not found in ${c.config.name} (functions: ${(c.config.actions || []).map(x => x.name).join(", ")})` };
            return { id: f.id, target: `${c.config.name}.${f.name}`, live: f };
        }
        return { error: "pass query=<name|id> or js_object=<name|id> + function=<name>" };
    };

    const results = [];
    for (const item of ITEMS) {
        const behaviour = String(item.behaviour || "").toUpperCase();
        if (!ALLOWED.includes(behaviour)) { results.push({ ...item, error: `behaviour must be one of ${ALLOWED.join(", ")}` }); continue; }
        if (behaviour === "AUTOMATIC" && !String(item.reason || "").trim()) {
            results.push({ ...item, error: "AUTOMATIC re-runs on every dependency change — prefer MANUAL (called from an event) or ON_PAGE_LOAD; pass `reason` only if it really must react automatically" });
            continue;
        }
        const r = resolve(item);
        if (r.error) { results.push({ ...item, error: r.error }); continue; }
        const resp = await fetch(`/api/v1/actions/runBehaviour/${r.id}?behaviour=${behaviour}`, {
            method: "PUT", credentials: "include", headers: { "X-XSRF-TOKEN": xsrf },
        });
        const j = await resp.json();
        if (!j.responseMeta?.success) {
            results.push({ target: r.target, id: r.id, error: j.responseMeta?.error?.message || `HTTP ${resp.status}` });
            continue;
        }
        try { r.live.runBehaviour = behaviour; } catch (e) { /* frozen state: the refetch below covers it */ }
        const out = { target: r.target, id: r.id, runBehaviour: behaviour };
        if (behaviour === "AUTOMATIC") out.reason = item.reason;
        results.push(out);
    }

    if (moduleId) store.dispatch({ type: "FETCH_MODULE_ENTITIES_INIT", payload: { moduleId } });
    else {
        const applicationId = state.ui.applications?.currentApplication?.id;
        if (applicationId) store.dispatch({ type: "FETCH_ACTIONS_INIT", payload: { applicationId } });
    }

    let onLoad = null;
    try {
        const url = moduleId ? `/api/v1/modules/${moduleId}` : `/api/v1/pages/${pageId}`;
        const jp = await (await fetch(url, { credentials: "include" })).json();
        onLoad = ((jp.data?.layouts?.[0]?.layoutOnLoadActions) || []).flat().map(x => ({ id: x.id, name: x.name }));
    } catch (e) {}
    return { results, onLoad };
})()
