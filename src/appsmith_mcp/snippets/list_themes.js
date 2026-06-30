(() => (window.__store.getState().ui.appTheming?.themes || []).map(t => ({
    id: t.id,
    name: t.name,
    displayName: t.displayName,
    isSystemTheme: !!t.isSystemTheme,
})))()
