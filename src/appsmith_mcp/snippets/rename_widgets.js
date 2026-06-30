(() => {
    const out = [];
    for (const u of UPDATES) {
        const cw = window.__store.getState().entities.canvasWidgets || {};
        if (!cw[u.widget_id]) { out.push({ widgetId: u.widget_id, error: "not found" }); continue; }
        window.__store.dispatch({
            type: "UPDATE_WIDGET_NAME_INIT",
            payload: { id: u.widget_id, newName: u.new_name },
        });
        out.push({ widgetId: u.widget_id, requestedName: u.new_name });
    }
    return out;
})()
