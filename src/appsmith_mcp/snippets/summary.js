(() => {
    const s = window.__store.getState();
    const cw = s.entities.canvasWidgets || {};
    const ds = s.entities.datasources?.list || [];
    const actions = s.entities.actions || [];
    return {
        widgets: { count: Object.keys(cw).length, types: [...new Set(Object.values(cw).map(w => w.type))] },
        datasources: ds.length,
        queries: actions.length,
    };
})()
