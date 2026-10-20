(async () => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    const w = cw[WIDGET_ID];
    if (!w) return { error: `widget ${WIDGET_ID} not found` };
    if (w.type !== "TABLE_WIDGET_V2") return { error: `widget is ${w.type}, not TABLE_WIDGET_V2` };

    const primary = { ...(w.primaryColumns || {}) };
    // `derivedColumns` holds the user-added (non-data) columns. A data-bound table regenerates
    // primaryColumns from tableData on save, dropping any added column that ISN'T a derived
    // column — so every column we add here must be marked isDerived + mirrored into derivedColumns.
    const derived = { ...(w.derivedColumns || {}) };
    let order = [...(w.columnOrder || Object.keys(primary))];
    let enableRowLevelEdit = false;
    const widgetName = w.widgetName;
    const escape = s => String(s).replace(/"/g, '\\"');
    const BUTTON_TYPES = ["button", "iconButton", "menuButton"];

    // Per-row cell props that only resolve when the value is an ARRAY mapped over
    // processedTableData (the loose `currentRow` only exists inside that .map). A caller naturally
    // writes `{{ currentRow.banido ? 'Reativar' : 'Inativar' }}`; without the wrap the button shows
    // the literal `{{ currentRow.b...` text (feedback 3.6). Wrap any such value here, and register
    // the path in dynamicBindingPathList below so it actually evaluates.
    const wrapCell = val => {
        if (typeof val !== "string" || !/\{\{/.test(val)) return val;            // static value — leave
        if (/processedTableData/.test(val) && /\.map\s*\(/.test(val)) return val; // already wrapped
        if (!/currentRow/.test(val)) return val;                                 // table-level binding, applies to all rows
        const inner = val.trim().replace(/^\{\{/, "").replace(/\}\}$/, "").trim();
        return `{{ ${widgetName}.processedTableData.map((currentRow, currentIndex) => ( ${inner} )) }}`;
    };
    // Cell props that carry a {{...}} binding (per-row or table-level) and so must be in
    // dynamicBindingPathList for the table to evaluate them.
    const CELL_BIND_PROPS = ["computedValue", "buttonLabel", "buttonColor", "buttonVariant", "menuColor",
        "isDisabled", "isCompact", "isCellVisible", "cellBackground", "textColor", "isVisible"];

    const sanitize = id => String(id).replace(/[^a-zA-Z0-9_]/g, "_");
    // Ids that carry no meaning for the reader: `id`, `id_x`, `x_id` (case-insensitive). Hidden
    // by default so a freshly generated table doesn't show raw key columns (feedback item 19).
    const looksLikeId = id => /^id$/i.test(id) || /^id[_A-Z]/.test(id) || /_id$/i.test(id);
    const NUMERIC_TYPES = new Set(["number", "currency"]);
    const buildColumn = (col, index) => {
        const id = col.id;
        const sanitizedId = sanitize(id);
        const label = col.label || id;
        // An onClick (or an explicit button-family columnType) makes this an action column.
        const columnType = col.columnType || (col.onClick ? "button" : "text");
        const isButton = BUTTON_TYPES.includes(columnType);
        // Sensible defaults matching what a human does on every table: numeric columns align
        // right; id-ish columns start hidden. Explicit align/hidden/width always win.
        const align = col.align || (NUMERIC_TYPES.has(columnType) ? "RIGHT" : "LEFT");
        const visible = col.hidden != null ? !col.hidden : !looksLikeId(id);
        const base = {
            allowCellWrapping: false, allowSameOptionsInNewRow: true,
            index, width: col.width || 150, originalId: id, id: sanitizedId, alias: id,
            horizontalAlignment: align, verticalAlignment: "CENTER",
            columnType, textColor: "", textSize: "0.875rem", fontStyle: "REGULAR",
            enableFilter: true, enableSort: true,
            isVisible: visible, isDisabled: false,
            isCellEditable: false, isEditable: false, isCellVisible: true,
            // Columns added through this tool are custom columns: mark them derived so the
            // table keeps them instead of regenerating the column set from tableData.
            isDerived: true, label, isSaveVisible: true, isDiscardVisible: true,
            sticky: "", validation: {},
            currencyCode: "BRL", decimals: columnType === "currency" ? 2 : 0, thousandSeparator: true, notation: "standard",
        };
        if (isButton) {
            // Action columns render a button/menu that fires onClick — no data computedValue.
            // columnType must be a button family for onClick to be treated as a trigger (a text
            // column's onClick is evaluated as data → "Data fields cannot execute framework
            // actions"). onClick is also registered in dynamicTriggerPathList below.
            base.computedValue = "";
            // Per-row dynamic props (label/color/variant/disabled/compact) are auto-wrapped in a
            // processedTableData.map so a `{{ currentRow... }}` expression resolves per row instead
            // of rendering as literal text; a static value passes through untouched.
            base.buttonLabel = wrapCell(col.buttonLabel || label);
            base.buttonVariant = col.buttonVariant != null ? wrapCell(col.buttonVariant) : "PRIMARY";
            if (col.buttonColor != null) base.buttonColor = wrapCell(col.buttonColor);
            if (col.isDisabled != null) base.isDisabled = wrapCell(col.isDisabled);
            if (col.isCompact != null) base.isCompact = wrapCell(col.isCompact);
            if (col.onClick) base.onClick = col.onClick;
            if (columnType === "menuButton" && Array.isArray(col.menuItems)) base.menuItems = col.menuItems;
        } else {
            // A derived data-mirror column: pull the field's value per row. The empty-table
            // fallback MUST be `[]` — a bare identifier (e.g. `: produto`) throws
            // `ReferenceError: <col> is not defined` on every empty load, littering the debugger
            // with per-column errors that vanish once data arrives (so they look intermittent).
            base.computedValue = `{{(() => { const tableData = ${widgetName}.processedTableData || []; return tableData.length > 0 ? tableData.map((currentRow, currentIndex) => (currentRow["${escape(id)}"])) : [] })()}}`;
        }
        return base;
    };

    // An editActions column (inline Save/Discard) is a custom column that drives ROW_LEVEL edit.
    const buildEditActions = (col, index) => {
        const id = col.id;
        const sanitizedId = sanitize(id);
        return {
            allowCellWrapping: false, allowSameOptionsInNewRow: true,
            index, width: 150, originalId: id, id: sanitizedId, alias: id,
            horizontalAlignment: "CENTER", verticalAlignment: "CENTER",
            columnType: "editActions", textColor: "", textSize: "0.875rem", fontStyle: "REGULAR",
            enableFilter: false, enableSort: false,
            isVisible: true, isDisabled: false,
            isCellEditable: false, isEditable: false, isCellVisible: true,
            isDerived: true, label: col.label || "Save / Discard",
            isSaveVisible: true, isDiscardVisible: true,
            // Save button (both label prop names are set for cross-version compatibility).
            saveButtonVariant: "PRIMARY", saveButtonColor: "rgb(3, 179, 101)",
            saveActionLabel: col.saveLabel || "Save", saveButtonLabel: col.saveLabel || "Save",
            saveBorderRadius: "0.375rem", saveIconAlign: "left",
            // Discard button.
            discardButtonVariant: "TERTIARY", discardButtonColor: "rgb(217, 25, 33)",
            discardActionLabel: col.discardLabel || "Discard", discardButtonLabel: col.discardLabel || "Discard",
            discardBorderRadius: "0.375rem", discardIconAlign: "left",
            onSave: col.onSave, onDiscard: col.onDiscard,
            computedValue: "", sticky: "", validation: {},
            currencyCode: "USD", decimals: 0, thousandSeparator: true, notation: "standard",
        };
    };

    const result = { added: [], removed: [], reordered: false, ignored: [], rejected: [] };

    if (Array.isArray(REMOVE) && REMOVE.length) {
        for (const id of REMOVE) {
            const sid = sanitize(id);
            if (primary[sid]) { delete primary[sid]; result.removed.push(sid); }
            else result.ignored.push({ op: "remove", id: sid, reason: "no such column" });
            delete derived[sid];
        }
        order = order.filter(id => primary[id]);
    }

    if (Array.isArray(ADD) && ADD.length) {
        for (const col of ADD) {
            const sid = sanitize(col.id);
            if (col.columnType === "editActions") {
                // A partial editActions column breaks the whole table, so refuse it unless
                // both handlers are present rather than synthesize half of it.
                if (!col.onSave || !col.onDiscard) {
                    result.rejected.push({
                        op: "add", id: col.id,
                        reason: "editActions column needs both onSave and onDiscard handlers ({{...}} query calls)",
                    });
                    continue;
                }
                enableRowLevelEdit = true;   // ROW_LEVEL save mode is what an editActions column drives
            }
            const built = col.columnType === "editActions" ? buildEditActions(col, order.length) : buildColumn(col, order.length);
            primary[sid] = built;
            derived[sid] = built;
            if (!order.includes(sid)) order.push(sid);
            result.added.push(sid);
        }
    }

    // Seed columns from a known schema when the table has no data yet (a data-bound table only
    // materializes primaryColumns once a row arrives). Builds proper data-mirror columns with the
    // `: []` fallback + binding paths, so the columns exist and render before any interaction.
    if (Array.isArray(FROM_SCHEMA) && FROM_SCHEMA.length) {
        result.seeded = [];
        for (const col of FROM_SCHEMA) {
            const sid = sanitize(col.id);
            if (primary[sid]) continue; // don't clobber an existing column
            const built = buildColumn(col, order.length);
            primary[sid] = built;
            derived[sid] = built;
            if (!order.includes(sid)) order.push(sid);
            result.seeded.push(sid);
        }
    }

    // Declarative tidy pass: rename/resize/align/hide existing columns in one call, no dotted
    // paths. `configure=[{id,label,width,align,hidden,columnType}]`.
    if (Array.isArray(CONFIGURE) && CONFIGURE.length) {
        result.configured = [];
        for (const col of CONFIGURE) {
            const sid = sanitize(col.id);
            if (!primary[sid]) {
                result.ignored.push({ op: "configure", id: sid, reason: "no such column — primaryColumns is only populated once the query has run (use from_schema to seed it)" });
                continue;
            }
            const c = { ...primary[sid] }; // clone — don't mutate the live Redux column object
            primary[sid] = c;
            if (col.label != null) c.label = col.label;
            if (col.width != null) c.width = col.width;
            if (col.align != null) c.horizontalAlignment = col.align;
            else if (NUMERIC_TYPES.has(col.columnType || c.columnType)) c.horizontalAlignment = c.horizontalAlignment || "RIGHT";
            if (col.hidden != null) c.isVisible = !col.hidden;
            if (col.columnType != null) c.columnType = col.columnType;
            // Make a data column editable in one go (needed for ROW_LEVEL inline edit).
            if (col.editable != null) { c.isEditable = !!col.editable; c.isCellEditable = !!col.editable; }
            // Formats the way the column pane stores them (Brazilian currency by default).
            if (c.columnType === "currency" && col.currencyCode == null && (!c.currencyCode || c.currencyCode === "USD")) c.currencyCode = "BRL";
            for (const k of ["currencyCode", "decimals", "thousandSeparator", "notation"]) if (col[k] != null) c[k] = col[k];
            if (col.dateInputFormat != null) c.inputFormat = col.dateInputFormat;
            if (col.dateOutputFormat != null) c.outputFormat = col.dateOutputFormat;
            if (derived[sid]) derived[sid] = c; // keep a derived (added) column mirrored; leave data columns alone
            result.configured.push(sid);
        }
    }

    // Hide every column not named in configure/from_schema — the "show only these" shortcut.
    if (HIDE_UNLISTED) {
        const keep = new Set([...(Array.isArray(CONFIGURE) ? CONFIGURE : []), ...(Array.isArray(FROM_SCHEMA) ? FROM_SCHEMA : [])].map(c => sanitize(c.id)));
        result.hidden = [];
        for (const sid of Object.keys(primary)) {
            if (!keep.has(sid) && primary[sid].isVisible !== false) {
                primary[sid] = { ...primary[sid], isVisible: false };
                if (derived[sid]) derived[sid] = primary[sid];
                result.hidden.push(sid);
            }
        }
    }

    if (Array.isArray(REORDER) && REORDER.length) {
        const sanitized = REORDER.map(sanitize);
        const known = sanitized.filter(id => primary[id]);
        const missing = Object.keys(primary).filter(id => !known.includes(id));
        order = [...known, ...missing];
        result.reordered = true;
    }
    // Reindex to match the final order.
    let i = 0;
    for (const id of order) {
        if (primary[id]) primary[id] = { ...primary[id], index: i++ };
        if (derived[id]) derived[id] = { ...derived[id], index: primary[id].index };
    }

    // Register every action column's onClick as a trigger path (not a binding), so the button
    // fires instead of being treated as a data field.
    const triggerList = (w.dynamicTriggerPathList || []).filter(p => !/^primaryColumns\./.test(p.key));
    for (const id of Object.keys(primary)) {
        // Any column handler (onClick, onSave/onDiscard of editActions, onSubmit, onOptionChange...)
        // is a trigger, classified by the key name.
        for (const [key, value] of Object.entries(primary[id] || {})) {
            if (/^on[A-Z]/.test(key) && typeof value === "string" && value.trim()) {
                triggerList.push({ key: `primaryColumns.${id}.${key}` });
            }
        }
    }
    const dedupe = arr => { const seen = new Set(); return arr.filter(p => (seen.has(p.key) ? false : seen.add(p.key))); };

    // Register every column cell prop that carries a {{...}} as a binding path, so buttonLabel/
    // buttonColor/computedValue/etc. actually evaluate (feedback 3.6: onClick became a trigger but
    // buttonLabel/buttonColor never entered dynamicBindingPathList and rendered as literal text).
    // Preserve the table's non-column bindings (e.g. tableData) and rebuild the primaryColumns ones.
    const bindingList = (w.dynamicBindingPathList || []).filter(p => !/^primaryColumns\./.test(p.key));
    for (const id of Object.keys(primary)) {
        // CELL_BIND_PROPS are the usual ones; any other non-handler prop carrying {{ }} is bound too
        // (otherwise Appsmith stores the text verbatim and the column renders blank).
        const props = new Set([...CELL_BIND_PROPS, ...Object.keys(primary[id] || {}).filter(k => !/^on[A-Z]/.test(k))]);
        for (const prop of props) {
            const v = primary[id] && primary[id][prop];
            if (typeof v === "string" && /\{\{/.test(v)) bindingList.push({ key: `primaryColumns.${id}.${prop}` });
        }
    }

    // Column props with a visual control (colour/switch/variant...) only show a per-row binding in
    // the column pane when the path is in dynamicPropertyPathList (the "JS" toggle) — mirror what
    // the editor stores. Code-editor props (computedValue, buttonLabel) never need it.
    const COLUMN_UI_PROPS = ["buttonColor", "menuColor", "textColor", "cellBackground", "buttonVariant",
        "menuVariant", "isDisabled", "isCompact", "isCellVisible", "isVisible", "isCellEditable",
        "allowCellWrapping", "horizontalAlignment", "verticalAlignment", "textSize", "fontStyle",
        "iconName", "borderRadius", "boxShadow"];
    const propertyList = (w.dynamicPropertyPathList || []).filter(p => !/^primaryColumns\./.test(p.key));
    for (const id of Object.keys(primary)) {
        for (const prop of COLUMN_UI_PROPS) {
            const v = primary[id] && primary[id][prop];
            if (typeof v === "string" && /\{\{/.test(v)) propertyList.push({ key: `primaryColumns.${id}.${prop}` });
        }
    }

    // Persist by writing the table node straight into the layout PUT via an override — NOT via a
    // BATCH_UPDATE dispatch. Dispatching kicks off a table saga that transiently resets
    // columnOrder to [] and schedules a debounced autosave, which races and overwrites this write.
    const override = { primaryColumns: primary, columnOrder: order, derivedColumns: derived, dynamicTriggerPathList: dedupe(triggerList), dynamicBindingPathList: dedupe(bindingList), dynamicPropertyPathList: dedupe(propertyList) };
    if (enableRowLevelEdit) override.inlineEditingSaveOption = "ROW_LEVEL";
    const p = await __persistLayout({ overrides: { [WIDGET_ID]: override } });

    // Keep the live client node consistent with what we just persisted. We must NOT dispatch
    // BATCH_UPDATE_WIDGET_PROPERTY for this (verified live: it fires a table saga that zeros
    // columnOrder ~1.5s later and schedules a racing autosave). Instead patch the (unfrozen)
    // Redux node directly — no dispatch, no saga. Without this, the client table node still has
    // the OLD columns, so the next __persistLayout (from add_widgets / update_widgets /
    // create_custom_widget) rebuilds the page DSL from that stale node and silently wipes these
    // columns from the backend — the "columns vanish after a later edit" bug from both feedbacks.
    if (p.persisted) {
        const live = (window.__store.getState().entities.canvasWidgets || {})[WIDGET_ID];
        if (live) {
            live.primaryColumns = primary;
            live.columnOrder = order;
            live.derivedColumns = derived;
            live.dynamicTriggerPathList = override.dynamicTriggerPathList;
            live.dynamicBindingPathList = override.dynamicBindingPathList;
            live.dynamicPropertyPathList = override.dynamicPropertyPathList;
            if (enableRowLevelEdit) live.inlineEditingSaveOption = "ROW_LEVEL";
        }
    }

    const res = { widgetId: WIDGET_ID, columnOrder: order, rowLevelEditEnabled: enableRowLevelEdit, ...result, note: "persisted; client state kept in sync so later widget writes won't drop these columns. The editor view refreshes on next page load." };
    if (p.persisted) res.persisted = true;
    else res.error = p.error || ("save failed: HTTP " + p.status);
    return res;
})()
