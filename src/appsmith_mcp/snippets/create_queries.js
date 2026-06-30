(async () => {
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    const out = [];
    let lastApplicationId = null;
    for (const q of QUERIES) {
        const s = window.__store.getState();
        const ds = (s.entities.datasources?.list || []).find(d => d.id === q.datasource_id);
        if (!ds) { out.push({ error: `datasource ${q.datasource_id} not found in current workspace`, name: q.name }); continue; }
        const applicationId = s.ui.applications?.currentApplication?.id;
        const pageId = q.page_id || s.entities.pageList?.currentPageId;
        const workspaceId = ds.workspaceId;
        lastApplicationId = applicationId;

        let actionConfig = q.action_config;
        if (!actionConfig || Object.keys(actionConfig).length === 0) {
            const plugin = (s.entities.plugins?.list || []).find(p => p.id === ds.pluginId);
            actionConfig = (DEFAULTS || {})[plugin?.packageName] || {};
        }

        const body = {
            name: q.name, pageId, workspaceId, applicationId,
            pluginId: ds.pluginId,
            datasource: { id: q.datasource_id },
            actionConfiguration: actionConfig,
        };
        const r = await fetch('/api/v1/actions', {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-XSRF-TOKEN': xsrf },
            body: JSON.stringify(body),
        });
        const j = await r.json();
        if (!j.responseMeta?.success) {
            out.push({ error: j.responseMeta?.error?.message || 'create failed', status: r.status, name: q.name });
            continue;
        }
        out.push({ id: j.data?.id, name: j.data?.name, pageId, datasourceId: q.datasource_id, actionConfiguration: actionConfig });
    }
    if (lastApplicationId) {
        window.__store.dispatch({ type: "FETCH_ACTIONS_INIT", payload: { applicationId: lastApplicationId } });
    }
    return out;
})()
