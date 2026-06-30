(() => {
    const out = [];
    for (const u of UPDATES) {
        const col = (window.__store.getState().entities.jsActions || []).find(j => j.config?.id === u.js_object_id);
        if (!col) { out.push({ error: `js object ${u.js_object_id} not found`, jsObjectId: u.js_object_id }); continue; }
        window.__store.dispatch({
            type: "UPDATE_JS_ACTION_BODY_INIT",
            payload: { id: u.js_object_id, body: u.body, isReplay: false },
        });
        out.push({ dispatched: true, id: u.js_object_id, name: col.config.name });
    }
    return out;
})()
