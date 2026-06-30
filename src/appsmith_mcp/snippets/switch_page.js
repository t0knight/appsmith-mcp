(() => {
    const pages = window.__store.getState().entities.pageList?.pages || [];
    const p = pages.find(x => x.pageId === PAGE_ID);
    if (!p) return { error: `page ${PAGE_ID} not found` };
    window.__store.dispatch({ type: "SWITCH_CURRENT_PAGE_ID", payload: { id: PAGE_ID, slug: p.slug, permissions: p.userPermissions } });
    return { dispatched: true, pageId: PAGE_ID };
})()
