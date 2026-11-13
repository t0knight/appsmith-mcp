(async () => {
    const store = window.__store;
    const colOf = (id) => (store.getState().entities.jsActions || []).find(j => j.config?.id === id);
    const out = [];
    for (const u of UPDATES) {
        const col = colOf(u.js_object_id);
        if (!col) { out.push({ error: `js object ${u.js_object_id} not found`, jsObjectId: u.js_object_id }); continue; }
        // UPDATE_JS_ACTION_BODY_INIT runs a saga that (a) re-parses the body into config.actions
        // — adding/removing member functions — and (b) persists to the backend. It is NOT
        // instant (~2s), so returning right after dispatch (the old behavior) reports stale
        // function names; we poll below until the re-parse lands before returning.
        store.dispatch({
            type: "UPDATE_JS_ACTION_BODY_INIT",
            payload: { id: u.js_object_id, body: u.body, isReplay: false },
        });
        out.push({ id: u.js_object_id, name: col.config.name, body: u.body, expected: u.function_names || null });
    }

    const state = (r) => {
        const col = colOf(r.id);
        return { names: (col?.config?.actions || []).map(a => a.name), body: col?.config?.body, loading: !!col?.isLoading };
    };
    const sameSet = (a, b) => a.length === b.length && a.every(n => b.includes(n));
    const settled = (r) => {
        if (r.error) return true;
        const s = state(r);
        if (s.loading) return false;
        if (s.body !== r.body) return false; // wait for the new body to be in place
        if (r.expected && r.expected.length) return sameSet(s.names, r.expected);
        return true;
    };

    const start = Date.now();
    while (Date.now() - start < 8000 && !out.every(settled)) {
        await new Promise(r => setTimeout(r, 150));
    }

    for (const r of out) {
        if (r.error) continue;
        const s = state(r);
        r.functionNames = s.names;
        const ok = s.body === r.body && (!r.expected || !r.expected.length || sameSet(s.names, r.expected));
        r.persisted = ok;
        if (!ok) r.warning = "re-parse did not settle within timeout (body/functions may be mid-save)";
        delete r.body;
        delete r.expected;
    }
    return out;
})()
