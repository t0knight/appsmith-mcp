(async () => {
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    // Auto-register bindings: walk actionConfiguration for {{...}} string leaves and record their
    // dotted paths (relative to actionConfiguration, e.g. "path", "body", "headers[1].value") in
    // the action's top-level dynamicBindingPathList — exactly the shape Appsmith persists. Without
    // this the `{{ }}` go literal ("Illegal character in path...", unevaluated bodies).
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
    let lastApplicationId = null;
    for (const q of QUERIES) {
        const s = window.__store.getState();
        const ds = (s.entities.datasources?.list || []).find(d => d.id === q.datasource_id);
        if (!ds) { out.push({ error: `datasource ${q.datasource_id} not found in current workspace`, name: q.name }); continue; }
        const applicationId = s.ui.applications?.currentApplication?.id;
        const moduleId = s.ui.editor?.currentModuleId || null;
        const pageId = moduleId ? null : (q.page_id || s.entities.pageList?.currentPageId);
        const workspaceId = ds.workspaceId;
        lastApplicationId = applicationId;

        let actionConfig = q.action_config;
        if (!actionConfig || Object.keys(actionConfig).length === 0) {
            const plugin = (s.entities.plugins?.list || []).find(p => p.id === ds.pluginId);
            actionConfig = (DEFAULTS || {})[plugin?.packageName] || {};
        }

        // Inside a package module the query belongs to the module (contextType MODULE), not a page.
        const owner = moduleId ? { moduleId, contextType: "MODULE" } : { pageId, applicationId };
        const body = {
            name: q.name, workspaceId, ...owner,
            pluginId: ds.pluginId,
            datasource: { id: q.datasource_id },
            actionConfiguration: actionConfig,
            dynamicBindingPathList: bindingPaths(actionConfig, q.dynamic_binding_paths),
        };
        // Settable at creation so a query does not need a follow-up update_queries call
        // just to stop running on page load.
        if (q.run_behaviour != null) body.runBehaviour = q.run_behaviour;
        if (q.confirm_before_execute != null) body.confirmBeforeExecute = q.confirm_before_execute;
        if (q.user_set_on_load != null) body.userSetOnLoad = q.user_set_on_load;
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
        out.push({ id: j.data?.id, name: j.data?.name, ...(moduleId ? { moduleId } : { pageId }), datasourceId: q.datasource_id,
                   runBehaviour: j.data?.runBehaviour, actionConfiguration: actionConfig });
    }
    const currentModuleId = window.__store.getState().ui.editor?.currentModuleId;
    if (currentModuleId) {
        window.__store.dispatch({ type: "FETCH_MODULE_ENTITIES_INIT", payload: { moduleId: currentModuleId } });
    } else if (lastApplicationId) {
        window.__store.dispatch({ type: "FETCH_ACTIONS_INIT", payload: { applicationId: lastApplicationId } });
    }
    return out;
})()
