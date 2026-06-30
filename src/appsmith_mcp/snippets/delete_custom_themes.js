(() => {
    const out = [];
    for (const e of THEMES) {
        const t = (window.__store.getState().ui.appTheming?.themes || []).find(t => t.id === e.theme_id);
        const name = e.name || t?.name;
        if (!name) { out.push({ error: `theme ${e.theme_id} not found and no name passed`, themeId: e.theme_id }); continue; }
        window.__store.dispatch({
            type: "DELETE_APP_THEME_INIT",
            payload: { themeId: e.theme_id, name },
        });
        out.push({ dispatched: true, themeId: e.theme_id, name });
    }
    return out;
})()
