(async () => {
    const origin = window.location.origin;
    const wsRes = await fetch('/api/v1/workspaces/home', { credentials: 'include', headers: {'Accept': 'application/json'} });
    const wsJson = await wsRes.json();
    const out = [];
    for (const ws of (wsJson.data || [])) {
        const r = await fetch(`/api/v1/applications/home?workspaceId=${ws.id}`, { credentials: 'include', headers: {'Accept': 'application/json'} });
        const j = await r.json();
        for (const a of (j.data || [])) {
            const p = (a.pages || []).find(x => x.isDefault) || (a.pages || [])[0] || {};
            out.push({
                id: a.id,
                name: a.name,
                slug: a.slug,
                workspaceId: a.workspaceId,
                defaultPageId: p.id,
                editorUrl: a.slug && p.baseId ? `${origin}/app/${a.slug}/page1-${p.baseId}/edit` : null,
            });
        }
    }
    return out;
})()
