(() => {
    const out = [];
    for (const id of COLLECTION_IDS) {
        const col = (window.__store.getState().entities.jsActions || []).find(j => j.config?.id === id);
        if (!col) { out.push({ error: `js object ${id} not found`, id }); continue; }
        window.__store.dispatch({
            type: "DELETE_JS_ACTION_INIT",
            payload: { id: col.config.id, name: col.config.name },
        });
        out.push({ dispatched: true, id, name: col.config.name });
    }
    return out;
})()
