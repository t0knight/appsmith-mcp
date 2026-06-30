(() => (window.__store.getState().ui.workspaces.list || []).map(w => ({id: w.id, name: w.name})))()
