(() => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    // A cheap flat map of the whole page: name -> id -> type -> parent -> grid box. This is
    // the "where is everything" question that export_page (hundreds of KB) and get_widget
    // (one heavy record) both answered too expensively.
    const out = [];
    for (const w of Object.values(cw)) {
        if (!w || w.type === "CANVAS_WIDGET") continue;
        out.push({
            id: w.widgetId,
            name: w.widgetName,
            type: w.type,
            parentId: w.parentId,
            leftColumn: w.leftColumn,
            topRow: w.topRow,
            rightColumn: w.rightColumn,
            bottomRow: w.bottomRow,
            isVisible: w.isVisible !== false,
        });
    }
    out.sort((a, b) => (a.topRow - b.topRow) || (a.leftColumn - b.leftColumn));
    return out;
})()
