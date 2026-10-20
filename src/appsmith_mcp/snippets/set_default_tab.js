(() => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    let w = cw[WIDGET_ID];
    if (!w) w = Object.values(cw).find(x => x && x.widgetName === WIDGET_ID);
    if (!w) return { error: `widget '${WIDGET_ID}' not found` };
    if (w.type !== "TABS_WIDGET") return { error: `widget is ${w.type}, not TABS_WIDGET` };
    const tabs = Object.values(w.tabsObj || {});

    // RESOLVE mode: VALUE is a tab reference (id / label / widgetId) to render. Non-resolve
    // mode: VALUE is the raw defaultTab string to write back verbatim (restore path).
    let toSet = VALUE;
    if (RESOLVE) {
        const target = tabs.find(t => t.id === VALUE || t.label === VALUE || t.widgetId === VALUE);
        if (!target) return { error: `tab '${VALUE}' not found`, available: tabs.map(t => ({ id: t.id, label: t.label })) };
        toSet = target.label;
    }
    const original = w.defaultTab;
    window.__store.dispatch({
        type: "BATCH_UPDATE_WIDGET_PROPERTY",
        payload: { widgetId: w.widgetId, updates: { modify: { defaultTab: toSet } } },
    });
    return { widgetId: w.widgetId, original, applied: toSet };
})()
