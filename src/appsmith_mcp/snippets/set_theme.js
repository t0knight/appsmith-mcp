(() => {
    const s = window.__store.getState();
    const applicationId = s.ui.applications?.currentApplication?.id;
    if (!applicationId) return { error: "no current application — open an app editor first" };
    const theme = (s.ui.appTheming?.themes || []).find(t => t.id === THEME_ID);
    if (!theme) return { error: `theme ${THEME_ID} not found`, knownThemeIds: (s.ui.appTheming?.themes || []).map(t => t.id) };
    window.__store.dispatch({
        type: "CHANGE_SELECTED_APP_THEME_INIT",
        payload: { applicationId, theme, shouldReplay: false },
    });
    return { dispatched: true, themeId: theme.id, name: theme.name };
})()
