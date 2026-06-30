(() => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    const w = cw[WIDGET_ID];
    if (!w) return null;
    return w;
})()
