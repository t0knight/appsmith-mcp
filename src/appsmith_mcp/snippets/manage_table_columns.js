(() => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    const w = cw[WIDGET_ID];
    if (!w) return { error: `widget ${WIDGET_ID} not found` };
    if (w.type !== "TABLE_WIDGET_V2") return { error: `widget is ${w.type}, not TABLE_WIDGET_V2` };

    const primary = { ...(w.primaryColumns || {}) };
    let order = [...(w.columnOrder || Object.keys(primary))];
    const widgetName = w.widgetName;
    const escape = s => String(s).replace(/"/g, '\\"');

    const sanitize = id => String(id).replace(/[^a-zA-Z0-9_]/g, "_");
    const buildColumn = (col, index) => {
        const id = col.id;
        const sanitizedId = sanitize(id);
        const label = col.label || id;
        const columnType = col.columnType || "text";
        const isDerived = !!col.isDerived;
        return {
            allowCellWrapping: false, allowSameOptionsInNewRow: true,
            index, width: 150, originalId: id, id: sanitizedId, alias: id,
            horizontalAlignment: "LEFT", verticalAlignment: "CENTER",
            columnType, textColor: "", textSize: "0.875rem", fontStyle: "REGULAR",
            enableFilter: true, enableSort: true,
            isVisible: true, isDisabled: false,
            isCellEditable: false, isEditable: false, isCellVisible: true,
            isDerived, label, isSaveVisible: true, isDiscardVisible: true,
            computedValue: isDerived ? "" :
                `{{(() => { const tableData = ${widgetName}.processedTableData || []; return tableData.length > 0 ? tableData.map((currentRow, currentIndex) => (currentRow["${escape(id)}"])) : ${escape(id)} })()}}`,
            sticky: "", validation: {},
            currencyCode: "USD", decimals: 0, thousandSeparator: true, notation: "standard",
        };
    };

    const result = { added: [], removed: [], reordered: false };

    if (Array.isArray(REMOVE) && REMOVE.length) {
        for (const id of REMOVE) {
            const sid = sanitize(id);
            if (primary[sid]) {
                delete primary[sid];
                result.removed.push(sid);
            }
        }
        order = order.filter(id => primary[id]);
    }

    if (Array.isArray(ADD) && ADD.length) {
        for (const col of ADD) {
            const sid = sanitize(col.id);
            primary[sid] = buildColumn(col, order.length);
            if (!order.includes(sid)) order.push(sid);
            result.added.push(sid);
        }
    }

    if (Array.isArray(REORDER) && REORDER.length) {
        const sanitized = REORDER.map(sanitize);
        const known = sanitized.filter(id => primary[id]);
        const missing = Object.keys(primary).filter(id => !known.includes(id));
        order = [...known, ...missing];
        // Reindex
        let i = 0;
        for (const id of order) {
            if (primary[id]) primary[id] = { ...primary[id], index: i++ };
        }
        result.reordered = true;
    } else {
        // Reindex after add/remove
        let i = 0;
        for (const id of order) {
            if (primary[id]) primary[id] = { ...primary[id], index: i++ };
        }
    }

    window.__store.dispatch({
        type: "BATCH_UPDATE_WIDGET_PROPERTY",
        payload: {
            widgetId: WIDGET_ID,
            updates: { modify: { primaryColumns: primary, columnOrder: order } },
        },
    });

    return { widgetId: WIDGET_ID, columnOrder: order, ...result };
})()
