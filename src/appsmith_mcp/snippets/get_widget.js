(() => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    // Accept a hex id OR a widget name — the name is what you have on first contact, and
    // hunting for the id meant exporting the whole page just to look one widget up.
    let w = cw[WIDGET_ID];
    if (!w) w = Object.values(cw).find(x => x && x.widgetName === WIDGET_ID);
    if (!w) return null;
    // Project down to just the requested keys when FIELDS is given.
    if (Array.isArray(FIELDS) && FIELDS.length) {
        const out = {};
        for (const f of FIELDS) if (f in w) out[f] = w[f];
        return out;
    }
    // Custom widgets carry srcDoc + uncompiledSrcDoc (HTML+CSS+JS, often tens of KB, duplicated).
    // Drop them unless the caller opts in — get_custom_widget returns the source for who wants it.
    if (!INCLUDE_SOURCE && (("srcDoc" in w) || ("uncompiledSrcDoc" in w))) {
        const { srcDoc, uncompiledSrcDoc, ...rest } = w;
        const bytes = v => (v == null ? 0 : JSON.stringify(v).length);
        rest.sourceOmitted = {
            srcDocBytes: bytes(srcDoc),
            uncompiledSrcDocBytes: bytes(uncompiledSrcDoc),
            note: "source stripped — pass include_source=true, or use get_custom_widget",
        };
        return rest;
    }
    return w;
})()
