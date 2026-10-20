(async () => {
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    // Recompute the action's dynamicBindingPathList from the FINAL actionConfiguration so {{...}}
    // in path/body/headers/queryParameters are actually evaluated (Appsmith stores these dotted
    // paths relative to actionConfiguration, e.g. "path", "body", "headers[1].value"). This also
    // repairs queries created without binding paths (dynamicBindingPathList: []).
    const bindRe = /\{\{[\s\S]*?\}\}/;
    const collectBindings = (val, prefix, out) => {
        if (typeof val === "string") { if (bindRe.test(val)) out.push(prefix); return; }
        if (Array.isArray(val)) { val.forEach((v, i) => collectBindings(v, `${prefix}[${i}]`, out)); return; }
        if (val && typeof val === "object") { for (const [k, v] of Object.entries(val)) collectBindings(v, prefix ? `${prefix}.${k}` : k, out); return; }
    };
    const bindingPaths = (actionConfig, extra) => {
        const keys = [];
        collectBindings(actionConfig, "", keys);
        // Extra paths may come as "body" or {key: "body"} (the server's query policy sends the latter).
        for (const e of (extra || [])) {
            const k = (e && typeof e === "object") ? e.key : e;
            if (typeof k === "string" && k && !keys.includes(k)) keys.push(k);
        }
        return keys.map(key => ({ key }));
    };
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
        if (u.datasource_id) {
            // Point the query at a saved datasource (same as picking it in the editor's URL
            // dropdown): the query then inherits the datasource's base URL + headers.
            const ds = (window.__store.getState().entities.datasources?.list || []).find(d => d.id === u.datasource_id);
            if (!ds) { out.push({ error: `datasource ${u.datasource_id} not found`, queryId: u.query_id }); continue; }
            if (ds.pluginId !== action.config.pluginId) { out.push({ error: `datasource ${ds.name} uses another plugin`, queryId: u.query_id }); continue; }
            merged.datasource = { id: ds.id, name: ds.name, pluginId: ds.pluginId, workspaceId: ds.workspaceId };
        }
        merged.dynamicBindingPathList = bindingPaths(merged.actionConfiguration, u.dynamic_binding_paths);
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
    const currentModuleId = window.__store.getState().ui.editor?.currentModuleId;
    if (currentModuleId) {
        window.__store.dispatch({ type: "FETCH_MODULE_ENTITIES_INIT", payload: { moduleId: currentModuleId } });
    } else if (applicationId) {
        window.__store.dispatch({ type: "FETCH_ACTIONS_INIT", payload: { applicationId } });
    }
    return out;
})()
