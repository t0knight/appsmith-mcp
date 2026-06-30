(() => {
    const s = window.__store.getState();
    const applicationId = s.ui.applications?.currentApplication?.id;
    const workspaceId = s.ui.selectedWorkspace?.workspace?.id;
    const jsPlugin = (s.entities.plugins?.list || []).find(p => p.type === "JS");
    if (!jsPlugin) return { error: "JS plugin not found" };
    const out = [];
    for (const o of OBJECTS) {
        const pageId = o.page_id || s.entities.pageList?.currentPageId;
        const actions = (o.function_names || []).map(name => ({
            name, workspaceId, pageId,
            pluginId: jsPlugin.id,
            actionConfiguration: { body: "" },
        }));
        window.__store.dispatch({
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
        out.push({ dispatched: true, name: o.name, pageId, functionNames: o.function_names });
    }
    return out;
})()
