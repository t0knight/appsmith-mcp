(() => {
    const applicationId = window.__store.getState().ui.applications?.currentApplication?.id;
    if (!applicationId) return { error: "no current application" };
    window.__store.dispatch({
        type: "SAVE_APP_THEME_INIT",
        payload: { applicationId, name: NAME },
    });
    return { dispatched: true, applicationId, name: NAME };
})()
