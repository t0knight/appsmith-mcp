(() => {
    const s = window.__store.getState();
    const applicationId = s.ui.applications?.currentApplication?.id;
    if (!applicationId) return { error: "no current application — open an app editor first" };
    const current = s.ui.appTheming?.selectedTheme;
    if (!current || !current.id) return { error: "no theme loaded" };
    // Deep-merge PROPERTIES into current.properties.{colors,fontFamily,borderRadius,boxShadow}.
    const next = JSON.parse(JSON.stringify(current));
    for (const [section, vals] of Object.entries(PROPERTIES || {})) {
        next.properties[section] = { ...(next.properties[section] || {}), ...vals };
    }
    window.__store.dispatch({
        type: "UPDATE_SELECTED_APP_THEME_INIT",
        payload: { applicationId, theme: next, shouldReplay: false },
    });
    return { dispatched: true, themeId: next.id, applied: PROPERTIES };
})()
