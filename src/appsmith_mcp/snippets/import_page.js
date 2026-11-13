(async () => {
    const s = window.__store.getState();
    const appId = s.ui.applications?.currentApplication?.id;
    const pid = PAGE_ID || s.entities.pageList.currentPageId;
    if (!appId || !pid) return { error: "no application/page open" };

    // The layoutId belongs to the page being written, not to whatever page is open.
    const meta = await fetch(`/api/v1/pages/${pid}?applicationId=${appId}`, {
        credentials: "include", headers: { Accept: "application/json" },
    }).then(r => r.json());
    const layoutId = meta.data?.layouts?.[0]?.id;
    if (!layoutId) return { error: "could not resolve the layout id for page " + pid };

    const r = await fetch(`/api/v1/layouts/${layoutId}/pages/${pid}?applicationId=${appId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ dsl: DSL }),
    });
    if (r.status < 200 || r.status >= 300) {
        let detail = null;
        try { detail = (await r.text()).slice(0, 300); } catch (e) {}
        return { error: `HTTP ${r.status}`, detail };
    }
    const count = (function walk(n) {
        return n ? 1 + (n.children || []).reduce((a, c) => a + walk(c), 0) : 0;
    })(DSL);
    return { restored: true, pageId: pid, layoutId, widgetCount: count,
             note: "reload the page (refresh_page) to rebuild the editor from the restored DSL" };
})()
