(() => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    let w = cw[WIDGET_ID];
    if (!w) w = Object.values(cw).find(x => x && x.widgetName === WIDGET_ID);
    if (!w) return { error: `widget '${WIDGET_ID}' not found` };
    if (w.type !== "MODAL_WIDGET") return { error: `widget is ${w.type}, not MODAL_WIDGET` };
    // SHOW_MODAL / CLOSE_MODAL are runtime actions (no persist) — the same ones update_widgets
    // delegates isVisible to, so previewing a modal never dirties the saved page.
    if (OPEN) {
        window.__store.dispatch({ type: "SHOW_MODAL", payload: { modalId: w.widgetId } });
    } else {
        window.__store.dispatch({ type: "CLOSE_MODAL", payload: { modalName: w.widgetName } });
    }
    return { ok: true, name: w.widgetName, opened: !!OPEN };
})()
