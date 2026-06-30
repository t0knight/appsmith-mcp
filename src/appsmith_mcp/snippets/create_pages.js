(() => {
    const s = window.__store.getState();
    const applicationId = s.ui.applications?.currentApplication?.id;
    if (!applicationId) return { error: "no current application — open an app editor first" };
    const out = [];
    for (const name of NAMES) {
        window.__store.dispatch({
            type: "CREATE_PAGE_INIT",
            payload: {
                applicationId, name,
                layouts: [{ dsl: { widgetName: "MainContainer", type: "CANVAS_WIDGET", widgetId: "0", children: [], leftColumn: 0, rightColumn: 0, topRow: 0, bottomRow: 0, version: 94 } }],
            },
        });
        out.push({ dispatched: true, name, applicationId });
    }
    return out;
})()
