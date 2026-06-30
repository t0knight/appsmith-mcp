(() => {
    const out = [];
    for (const id of PAGE_IDS) {
        window.__store.dispatch({ type: "DELETE_PAGE_INIT", payload: { id } });
        out.push({ dispatched: true, pageId: id });
    }
    return out;
})()
