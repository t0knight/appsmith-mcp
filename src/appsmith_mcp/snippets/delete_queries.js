(() => {
    const out = [];
    for (const id of ACTION_IDS) {
        const a = (window.__store.getState().entities.actions || []).find(x => x.config?.id === id);
        if (!a) { out.push({ error: `query ${id} not found in store`, id }); continue; }
        window.__store.dispatch({ type: "DELETE_ACTION_INIT", payload: { id: a.config.id, name: a.config.name } });
        out.push({ dispatched: true, id });
    }
    return out;
})()
