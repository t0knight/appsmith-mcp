(() => {
    const want = new Set(IDS || []);
    return (window.__store.getState().entities.jsActions || [])
        .filter(j => want.size === 0 || want.has(j.config?.id))
        .map(j => ({
            id: j.config?.id,
            name: j.config?.name,
            pageId: j.config?.pageId,
            body: j.config?.body,
            actions: (j.config?.actions || []).map(a => ({
                id: a.id, name: a.name, body: a.actionConfiguration?.body,
            })),
            variables: j.config?.variables,
        }));
})()
