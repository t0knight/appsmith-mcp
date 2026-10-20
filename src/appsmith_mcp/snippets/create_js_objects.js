(async () => {
    const store = window.__store;
    const s = store.getState();
    const applicationId = s.ui.applications?.currentApplication?.id;
    const workspaceId = s.ui.selectedWorkspace?.workspace?.id;
    const jsPlugin = (s.entities.plugins?.list || []).find(p => p.type === "JS");
    if (!jsPlugin) return { error: "JS plugin not found" };

    // Inside a package module editor, JS objects belong to the module: create them the way the
    // module editor does (POST collections/actions with moduleId + contextType MODULE).
    const moduleId = s.ui.editor?.currentModuleId;
    if (moduleId) {
        const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
        const out = [];
        for (const o of OBJECTS) {
            const body = {
                name: o.name, workspaceId, pluginId: jsPlugin.id, pluginType: "JS", body: o.body, variables: [],
                actions: (o.function_names || []).map(name => ({
                    name, workspaceId, runBehaviour: "MANUAL", clientSideExecution: true,
                    actionConfiguration: { body: "", timeoutInMillisecond: 0, jsArguments: [] },
                })),
                moduleId, contextType: "MODULE",
            };
            const r = await fetch('/api/v1/collections/actions', {
                method: 'POST', credentials: 'include',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-XSRF-TOKEN': xsrf },
                body: JSON.stringify(body),
            });
            const j = await r.json();
            if (!j.responseMeta?.success) { out.push({ name: o.name, error: j.responseMeta?.error?.message || 'create failed', status: r.status }); continue; }
            out.push({ name: o.name, moduleId, functionNames: o.function_names, id: j.data?.id || null });
        }
        store.dispatch({ type: "FETCH_MODULE_ENTITIES_INIT", payload: { moduleId } });
        return out;
    }

    const before = new Set((store.getState().entities.jsActions || []).map(j => j.config?.id));
    const requested = [];
    for (const o of OBJECTS) {
        const pageId = o.page_id || s.entities.pageList?.currentPageId;
        const actions = (o.function_names || []).map(name => ({
            name, workspaceId, pageId,
            pluginId: jsPlugin.id,
            actionConfiguration: { body: "" },
        }));
        store.dispatch({
            type: "CREATE_JS_ACTION_INIT",
            payload: {
                request: {
                    name: o.name,
                    pageId, applicationId, workspaceId,
                    pluginId: jsPlugin.id,
                    pluginType: "JS",
                    body: o.body,
                    variables: [],
                    actions,
                },
                from: "JS_OBJECT_GUTTER_RUN_BUTTON",
            },
        });
        requested.push({ name: o.name, pageId, functionNames: o.function_names });
    }

    // CREATE_JS_ACTION_INIT is a saga that mints the real collection id; poll jsActions so
    // the caller gets the id needed for execute_js_functions / patch_js_objects.
    const wanted = new Set(OBJECTS.map(o => o.name));
    const found = {};
    const start = Date.now();
    while (Date.now() - start < 8000 && Object.keys(found).length < OBJECTS.length) {
        for (const j of (store.getState().entities.jsActions || [])) {
            const c = j.config || {};
            if (!before.has(c.id) && wanted.has(c.name) && !found[c.name]) found[c.name] = c.id;
        }
        if (Object.keys(found).length >= OBJECTS.length) break;
        await new Promise(r => setTimeout(r, 200));
    }

    return requested.map(o => ({ dispatched: true, name: o.name, pageId: o.pageId, functionNames: o.functionNames, id: found[o.name] || null }));
})()
