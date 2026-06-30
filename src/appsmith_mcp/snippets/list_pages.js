(() => {
    const s = window.__store.getState();
    const pages = s.entities.pageList?.pages || [];
    const currentPageId = s.entities.pageList?.currentPageId || null;
    return pages.map(p => ({
        id: p.pageId, name: p.pageName, isDefault: !!p.isDefault, isHidden: !!p.isHidden,
        slug: p.slug, isCurrent: p.pageId === currentPageId,
    }));
})()
