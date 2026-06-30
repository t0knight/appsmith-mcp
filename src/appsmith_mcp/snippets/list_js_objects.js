(() => (window.__store.getState().entities.jsActions || []).map(j => ({
    id: j.config?.id,
    name: j.config?.name,
    pageId: j.config?.pageId,
    actions: (j.config?.actions || []).map(a => ({ id: a.id, name: a.name })),
})))()
