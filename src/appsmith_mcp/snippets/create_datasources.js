(async () => {
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    const out = [];
    let lastWorkspaceId = null;
    for (const d of DATASOURCES) {
        const s = window.__store.getState();
        const workspaceId = d.workspace_id || s.ui.selectedWorkspace?.workspace?.id;
        const sample = (s.entities.datasources?.list || [])[0];
        const envId = (sample && Object.keys(sample.datasourceStorages || {})[0]) || "unused_env";
        lastWorkspaceId = workspaceId;

        let dsConfig = d.datasource_config;
        if (!dsConfig || Object.keys(dsConfig).length === 0) {
            const plugin = (s.entities.plugins?.list || []).find(p => p.id === d.plugin_id);
            const template = (DEFAULTS || {})[plugin?.packageName];
            if (template) {
                dsConfig = JSON.parse(JSON.stringify(template));
                if (d.url && "url" in dsConfig) dsConfig.url = d.url;
            } else {
                dsConfig = d.url
                    ? { url: d.url, headers: [], queryParameters: [] }
                    : {};
            }
        }

        const body = {
            name: d.name, workspaceId, pluginId: d.plugin_id,
            datasourceStorages: {
                [envId]: {
                    datasourceId: "", environmentId: envId,
                    datasourceConfiguration: dsConfig,
                    isValid: true,
                },
            },
        };
        const r = await fetch('/api/v1/datasources', {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-XSRF-TOKEN': xsrf },
            body: JSON.stringify(body),
        });
        const j = await r.json();
        if (!j.responseMeta?.success) {
            out.push({ error: j.responseMeta?.error?.message || 'create failed', status: r.status, name: d.name });
            continue;
        }
        out.push({ id: j.data?.id, name: j.data?.name, pluginId: j.data?.pluginId, workspaceId, datasourceConfiguration: dsConfig });
    }
    if (lastWorkspaceId) {
        window.__store.dispatch({ type: "FETCH_DATASOURCES_INIT", payload: { workspaceId: lastWorkspaceId } });
    }
    return out;
})()
