(() => {
    const out = [];
    for (const id of DATASOURCE_IDS) {
        window.__store.dispatch({ type: "DELETE_DATASOURCE_INIT", payload: { id } });
        out.push({ dispatched: true, id });
    }
    return out;
})()
