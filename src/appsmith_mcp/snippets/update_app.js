(() => {
    const s = window.__store.getState();
    const appId = APP_ID || s.ui.applications?.currentApplication?.id;
    if (!appId) return { error: "no app id and no current application" };
    const data = {};
    if (NAME) data.name = NAME;
    if (ICON) data.icon = ICON;
    if (COLOR) data.color = COLOR;

    const detail = {};
    if (NAVIGATION && Object.keys(NAVIGATION).length) detail.navigationSetting = NAVIGATION;
    if (THEME_SETTINGS && Object.keys(THEME_SETTINGS).length) detail.themeSetting = THEME_SETTINGS;
    if (POSITIONING && Object.keys(POSITIONING).length) detail.appPositioning = POSITIONING;
    if (Object.keys(detail).length) data.applicationDetail = detail;

    if (Object.keys(data).length === 0) {
        return { error: "nothing to update — pass name/icon/color/navigation/theme_settings/positioning" };
    }
    window.__store.dispatch({
        type: "UPDATE_APPLICATION",
        payload: { id: appId, ...data },
    });
    return { dispatched: true, id: appId, applied: data };
})()
