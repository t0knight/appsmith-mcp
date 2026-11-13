(() => {
    // The resolved style block of a widget (color/border/shadow/radius/typography), so callers
    // stop reading these one prop at a time via run_command.
    const w = (window.__store.getState().entities.canvasWidgets || {})[WIDGET_ID];
    if (!w) return { error: `widget ${WIDGET_ID} not found` };
    const STYLE = [
        "backgroundColor", "borderColor", "borderWidth", "borderRadius", "boxShadow",
        "boxShadowColor", "borderOpacity", "accentColor", "primaryColor", "textColor",
        "cellBackground", "buttonColor", "buttonVariant", "headerRowColor", "headerTextColor",
        "fontFamily", "fontSize", "fontStyle", "textAlign", "labelTextColor", "labelTextSize",
    ];
    const style = {};
    for (const k of STYLE) if (k in w) style[k] = w[k];
    return { id: w.widgetId, name: w.widgetName, type: w.type, style };
})()
