(async () => {
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    const out = [];
    let lastWorkspaceId = null;
    for (const u of UPDATES) {
        const ds = (window.__store.getState().entities.datasources?.list || []).find(d => d.id === u.datasource_id);
        if (!ds) { out.push({ error: `datasource ${u.datasource_id} not found`, datasourceId: u.datasource_id }); continue; }
        const next = JSON.parse(JSON.stringify(ds));
        if (u.name) next.name = u.name;
        if (u.datasource_config && Object.keys(u.datasource_config).length) {
            for (const envId of Object.keys(next.datasourceStorages || {})) {
                const cur = next.datasourceStorages[envId].datasourceConfiguration || {};
                next.datasourceStorages[envId].datasourceConfiguration = { ...cur, ...u.datasource_config };
            }
        }
        const r = await fetch(`/api/v1/datasources/${u.datasource_id}`, {
            method: 'PUT', credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-XSRF-TOKEN': xsrf },
            body: JSON.stringify(next),
        });
        const j = await r.json();
        if (!j.responseMeta?.success) {
            out.push({ error: j.responseMeta?.error?.message || 'update failed', status: r.status, datasourceId: u.datasource_id });
            continue;
        }
        lastWorkspaceId = ds.workspaceId;
        out.push({ id: j.data?.id, name: j.data?.name });
    }
    if (lastWorkspaceId) {
        window.__store.dispatch({ type: "FETCH_DATASOURCES_INIT", payload: { workspaceId: lastWorkspaceId } });
    }
    return out;
})()
