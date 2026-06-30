(() => {
    const out = [];
    for (const spec of WIDGETS) {
        const cw = window.__store.getState().entities.canvasWidgets || {};
        const parentId = spec.parent_id || "0";
        if (!cw[parentId]) { out.push({ error: `parent ${parentId} not found`, spec }); continue; }
        const id = spec.new_id || ("w_" + Math.random().toString(36).slice(2, 10));
        window.__store.dispatch({
            type: "WIDGET_ADD_CHILD",
            payload: {
                widgetId: parentId, type: spec.widget_type, newWidgetId: id,
                leftColumn: spec.left, topRow: spec.top,
                columns: spec.columns, rows: spec.rows,
                parentRowSpace: 10, parentColumnSpace: 10,
                props: {},
            },
        });
        const modify = { ...(spec.props || {}) };
        if (spec.name) modify.widgetName = spec.name;
        if (Object.keys(modify).length) {
            window.__store.dispatch({
                type: "BATCH_UPDATE_WIDGET_PROPERTY",
                payload: { widgetId: id, updates: { modify } },
            });
        }
        const w = window.__store.getState().entities.canvasWidgets[id];
        out.push({ widgetId: id, widgetName: w?.widgetName, type: w?.type, parent: w?.parentId });
    }
    return out;
})()
