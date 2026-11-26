(() => {
    // Saved configuration of the requested queries plus their plugin package name, which the
    // read-only execution policy needs to pick the rule that applies (SQL, REST, GraphQL, ...).
    const state = window.__store.getState();
    const plugins = state.entities.plugins?.list || [];
    const wanted = new Set(IDS);
    return (state.entities.actions || [])
        .filter(a => a.config && wanted.has(a.config.id))
        .map(({ config: c }) => ({
            id: c.id,
            name: c.name,
            pluginPackageName: plugins.find(p => p.id === c.pluginId)?.packageName,
            actionConfiguration: c.actionConfiguration,
        }));
})()
