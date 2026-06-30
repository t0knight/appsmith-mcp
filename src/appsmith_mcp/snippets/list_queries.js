(() => (window.__store.getState().entities.actions || []).map(a => ({
    id: a.config?.id, name: a.config?.name, pageId: a.config?.pageId,
    pluginId: a.config?.pluginId, datasourceId: a.config?.datasource?.id,
    httpMethod: a.config?.actionConfiguration?.httpMethod,
    path: a.config?.actionConfiguration?.path,
})))()
