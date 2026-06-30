(() => (window.__store.getState().entities.plugins?.list || []).map(p => ({
    id: p.id, name: p.name, packageName: p.packageName, type: p.type,
})))()
