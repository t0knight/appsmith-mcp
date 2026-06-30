(() => {
    const state = window.__store.getState();
    const cw = state.entities.canvasWidgets || {};
    const parentId = PARENT_ID || "0";
    const parent = cw[parentId];
    if (!parent) return { error: `parent ${parentId} not found` };

    // Width: fill the parent canvas's full column count.
    const columns = parent.snapColumns || 64;

    // Height: auto-height so the box tracks the content (the widget CSS sets the content
    // to a 16:9 ratio via ui-width). This stays correct across editor/preview where the
    // widget's pixel width differs — a fixed row count overflows in preview. `rows` here
    // is just a sensible starting estimate (16:9 at the current width).
    const rowSpace = parent.parentRowSpace || 10;
    const canvasDom = document.querySelector(`.appsmith_widget_${parentId}`);
    const widthPx = canvasDom ? canvasDom.getBoundingClientRect().width : window.innerWidth;
    const availPx = widthPx * 0.5625;
    const rows = availPx ? Math.max(4, Math.floor(availPx / rowSpace)) : (parent.bottomRow || 30);

    const id = "w_" + Math.random().toString(36).slice(2, 10);
    window.__store.dispatch({
        type: "WIDGET_ADD_CHILD",
        payload: {
            widgetId: parentId, type: "CUSTOM_WIDGET", newWidgetId: id,
            leftColumn: 0, topRow: 0, columns, rows,
            parentRowSpace: rowSpace, parentColumnSpace: parent.parentColumnSpace || 10,
            props: {},
        },
    });

    const modify = {
        ...(PROPS || {}),
        dynamicHeight: "AUTO_HEIGHT",
        minDynamicHeight: 4,
        maxDynamicHeight: 200,
    };
    if (NAME) modify.widgetName = NAME;
    window.__store.dispatch({
        type: "BATCH_UPDATE_WIDGET_PROPERTY",
        payload: { widgetId: id, updates: { modify } },
    });

    // Seeded source: write to both srcDoc and uncompiledSrcDoc via the persisting saga so
    // a reload / editor-pane interaction can't recompile stale uncompiled source over it.
    if (SEED) {
        window.__store.dispatch({
            type: "UPDATE_WIDGET_PROPERTY_REQUEST",
            payload: { widgetId: id, propertyPath: "srcDoc", propertyValue: SRC },
        });
        window.__store.dispatch({
            type: "UPDATE_WIDGET_PROPERTY_REQUEST",
            payload: { widgetId: id, propertyPath: "uncompiledSrcDoc", propertyValue: SRC },
        });
    }

    const w = window.__store.getState().entities.canvasWidgets[id];
    return {
        widgetId: id, widgetName: w?.widgetName, type: w?.type, parent: w?.parentId,
        columns, rows, measuredHeightPx: availPx, synced: SEED,
    };
})()
