(async () => {
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    const out = [];
    for (const u of UPDATES) {
        const action = (window.__store.getState().entities.actions || []).find(a => a.config?.id === u.query_id);
        if (!action) { out.push({ error: `query ${u.query_id} not found`, queryId: u.query_id }); continue; }
        const merged = { ...action.config };
        if (u.name) merged.name = u.name;
        if (u.action_config && Object.keys(u.action_config).length) {
            merged.actionConfiguration = { ...action.config.actionConfiguration, ...u.action_config };
        }
        if (u.run_behaviour) merged.runBehaviour = u.run_behaviour;
        delete merged.eventData; delete merged.isValid;
        const r = await fetch(`/api/v1/actions/${u.query_id}`, {
            method: 'PUT', credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-XSRF-TOKEN': xsrf },
            body: JSON.stringify(merged),
        });
        const j = await r.json();
        if (!j.responseMeta?.success) {
            out.push({ error: j.responseMeta?.error?.message || 'update failed', status: r.status, queryId: u.query_id });
            continue;
        }
        out.push({ id: j.data?.id, name: j.data?.name, actionConfiguration: j.data?.actionConfiguration });
    }
    const applicationId = window.__store.getState().ui.applications?.currentApplication?.id;
    if (applicationId) {
        window.__store.dispatch({ type: "FETCH_ACTIONS_INIT", payload: { applicationId } });
    }
    return out;
})()
