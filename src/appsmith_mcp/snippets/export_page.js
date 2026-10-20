(async () => {
    const s = window.__store.getState();
    const appId = s.ui.applications?.currentApplication?.id;
    const pid = PAGE_ID || s.entities.pageList.currentPageId;
    if (!appId || !pid) return { error: "no application/page open" };
    const r = await fetch(`/api/v1/pages/${pid}?applicationId=${appId}`, {
        credentials: "include", headers: { Accept: "application/json" },
    });
    const j = await r.json();
    if (!j.responseMeta?.success) {
        return { error: j.responseMeta?.error?.message || `HTTP ${r.status}` };
    }
    const layout = j.data?.layouts?.[0];
    const page = (s.entities.pageList.pages || []).find(p => p.pageId === pid);
    const count = (function walk(n) {
        return n ? 1 + (n.children || []).reduce((a, c) => a + walk(c), 0) : 0;
    })(layout?.dsl);
    return {
        applicationId: appId,
        pageId: pid,
        pageName: page ? page.pageName : j.data?.name,
        layoutId: layout?.id,
        widgetCount: count,
        dsl: layout?.dsl,
    };
})()
