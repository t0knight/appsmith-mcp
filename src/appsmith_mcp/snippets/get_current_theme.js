(() => {
    const t = window.__store.getState().ui.appTheming?.selectedTheme;
    if (!t || !t.id) return { error: "no theme loaded — open an app editor first" };
    return {
        id: t.id, name: t.name, displayName: t.displayName, isSystemTheme: !!t.isSystemTheme,
        properties: t.properties,
    };
})()
