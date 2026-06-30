(() => (window.__store.getState().entities.datasources?.list || []).map(d => ({
    id: d.id, name: d.name, pluginId: d.pluginId, workspaceId: d.workspaceId,
})))()
