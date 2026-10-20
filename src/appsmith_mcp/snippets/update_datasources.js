(async () => {
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    const out = [];
    let lastWorkspaceId = null;
    for (const u of UPDATES) {
        const ds = (window.__store.getState().entities.datasources?.list || []).find(d => d.id === u.datasource_id);
        if (!ds) { out.push({ error: `datasource ${u.datasource_id} not found`, datasourceId: u.datasource_id }); continue; }
        const next = JSON.parse(JSON.stringify(ds));
        if (u.name) next.name = u.name;
        const put = async (url, body) => {
            const r = await fetch(url, {
                method: 'PUT', credentials: 'include',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-XSRF-TOKEN': xsrf },
                body: JSON.stringify(body),
            });
            const j = await r.json();
            return { ok: !!j.responseMeta?.success, status: r.status, j };
        };
        let failed = null;
        let saved = null;
        if (u.name) {
            const res = await put(`/api/v1/datasources/${u.datasource_id}`, next);
            if (!res.ok) failed = res; else saved = res.j.data;
        }
        // Per-environment config (url, headers, auth...) is NOT persisted by PUT /datasources/{id};
        // the editor saves it through PUT /datasources/datasource-storages, one call per environment.
        const environments = [];
        if (!failed && u.datasource_config && Object.keys(u.datasource_config).length) {
            for (const [envId, storage] of Object.entries(next.datasourceStorages || {})) {
                const cur = storage.datasourceConfiguration || {};
                const body = {
                    ...storage,
                    datasourceId: ds.id,
                    environmentId: storage.environmentId || envId,
                    datasourceConfiguration: { ...cur, ...u.datasource_config },
                };
                const res = await put('/api/v1/datasources/datasource-storages', body);
                if (!res.ok) { failed = res; break; }
                environments.push(body.environmentId);
            }
        }
        if (failed) {
            out.push({ error: failed.j.responseMeta?.error?.message || 'update failed', status: failed.status, datasourceId: u.datasource_id });
            continue;
        }
        lastWorkspaceId = ds.workspaceId;
        out.push({ id: ds.id, name: saved?.name || next.name, environments });
    }
    if (lastWorkspaceId) {
        window.__store.dispatch({ type: "FETCH_DATASOURCES_INIT", payload: { workspaceId: lastWorkspaceId } });
    }
    return out;
})()
