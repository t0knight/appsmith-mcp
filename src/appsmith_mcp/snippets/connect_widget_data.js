(async () => {
    // Connect a table/select to a query the way the property pane's Data dropdown does:
    // `{{query.data}}` (no JS mode), and for tables the editor-style data columns
    // (isDerived:false, processedTableData.map computedValue) with readable labels and formats.
    const store = window.__store;
    const state = store.getState();
    const cw = state.entities.canvasWidgets || {};
    const w = cw[WIDGET_ID];
    if (!w) return { error: `widget ${WIDGET_ID} not found` };

    const actions = state.entities.actions || [];
    let action = actions.find(a => a.config && (a.config.name === QUERY || a.config.id === QUERY));
    let qname = action && action.config.name;
    let inst = null;
    if (!action) {
        // A package query-module instance is referenced by its instance name ({{inst.data}}); its
        // result lives on the instance's public action.
        inst = Object.values(state.entities.moduleInstances || {})
            .find(i => i && (i.name === QUERY || i.id === QUERY) && i.type === "QUERY_MODULE") || null;
        if (inst) {
            qname = inst.name;
            const pubs = (state.entities.moduleInstanceEntities && state.entities.moduleInstanceEntities.actions) || [];
            action = pubs.find(a => a.config && a.config.moduleInstanceId === inst.id && a.config.isPublic)
                || { config: { name: inst.name }, data: null };
        }
    }
    if (!action) return { error: `query ${QUERY} not found on this page — list_queries / list_module_instances show the available names` };
    const binding = `{{${qname}.data}}`;

    const body = Array.isArray(SAMPLE) ? SAMPLE : (action.data && action.data.body);
    const rows = Array.isArray(body) ? body.filter(r => r && typeof r === "object" && !Array.isArray(r)) : [];
    if (!rows.length && SAMPLE === null && w.type === "TABLE_WIDGET_V2" && (action.config.id || inst)) {
        // No result in the editor yet: let the caller run the query first — but only a read-only one.
        let sql = String((action.config.actionConfiguration || {}).body || "");
        let pluginType = action.config.pluginType;
        if (inst) {
            // An instance only exposes a stub; read the SQL from the package module it comes from.
            try {
                const pub = (await (await fetch(`/api/v1/modules/${inst.sourceModuleId}`, { credentials: "include" })).json()).data || {};
                const ents = (await (await fetch(`/api/v1/modules/${pub.originModuleId || inst.sourceModuleId}/entities`, { credentials: "include" })).json()).data || {};
                const src = (ents.actions || []).find(a => a.isPublic) || (ents.actions || [])[0] || {};
                sql = String((src.actionConfiguration || {}).body || "");
                pluginType = src.pluginType;
            } catch (e) { sql = ""; }
        }
        const readOnly = pluginType === "DB" && /^\s*(select|with)\b/i.test(sql)
            && !/\b(insert|update|delete|merge|drop|alter|create|truncate|exec|execute|grant|revoke|into)\b/i.test(sql);
        return inst ? { needsSample: true, instanceId: inst.id, readOnly } : { needsSample: true, queryId: action.config.id, readOnly };
    }
    const sampleKeys = [];
    for (const r of rows.slice(0, 50)) for (const k of Object.keys(r)) if (!sampleKeys.includes(k)) sampleKeys.push(k);

    const SELECTS = ["SELECT_WIDGET", "MULTI_SELECT_WIDGET_V2"];
    if (SELECTS.includes(w.type)) {
        const props = { sourceData: binding };
        if (LABEL_FIELD) props.optionLabel = LABEL_FIELD;
        if (VALUE_FIELD) props.optionValue = VALUE_FIELD;
        const missing = [LABEL_FIELD, VALUE_FIELD].filter(f => f && sampleKeys.length && !sampleKeys.includes(f));
        const policy = __propertyPolicy({ widget: w, props, replaceKeys: ["sourceData", "tableData"] });
        store.dispatch({ type: "BATCH_UPDATE_WIDGET_PROPERTY", payload: { widgetId: WIDGET_ID, updates: { modify: policy.modify } } });
        const p = await __persistLayout({ overrides: { [WIDGET_ID]: policy.modify } });
        const res = { widgetId: WIDGET_ID, widgetName: w.widgetName, query: qname, sourceData: binding,
            optionLabel: props.optionLabel ?? w.optionLabel, optionValue: props.optionValue ?? w.optionValue,
            applied: policy.registered };
        if (!LABEL_FIELD || !VALUE_FIELD) res.warning = "pass label_field and value_field (query column names) so the options show the right text/value";
        if (missing.length) res.warning = `fields not found in ${qname}'s last result: ${missing.join(", ")} (columns: ${sampleKeys.join(", ")})`;
        if (p.persisted) res.persisted = true; else res.error = p.error || ("save failed: HTTP " + p.status);
        return res;
    }
    if (w.type !== "TABLE_WIDGET_V2") return { error: `widget is ${w.type}; connect_widget_data supports TABLE_WIDGET_V2, ${SELECTS.join(", ")}` };

    const sanitize = id => String(id).replace(/[^a-zA-Z0-9_]/g, "_");
    const looksLikeId = id => /^id$/i.test(id) || /^id[_A-Z]/.test(id) || /_id$/i.test(id);
    const humanize = id => {
        const s = String(id).replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/[_\-]+/g, " ").trim().toLowerCase();
        return s ? s[0].toUpperCase() + s.slice(1) : String(id);
    };
    const DATE_TIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
    const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
    const infer = key => {
        const vals = rows.map(r => r[key]).filter(v => v !== null && v !== undefined && v !== "").slice(0, 20);
        if (!vals.length) return { columnType: "text" };
        // SQL Server datetimes arrive as epoch milliseconds: trust the number only with a date-like name.
        const DATE_NAME = /(^|_)(data|dt|date|dia|hora)(_|$)|_(em|at)$|^(created|updated|modified)|nascimento|admissao|demissao|vencimento|emissao/i;
        if (DATE_NAME.test(key) && vals.every(v => Number.isInteger(v) && v > 1e11 && v < 1e14))
            return { columnType: "date", inputFormat: "Milliseconds", outputFormat: "DD/MM/YYYY HH:mm" };
        if (vals.every(v => typeof v === "number")) return { columnType: "number" };
        if (vals.every(v => typeof v === "boolean")) return { columnType: "checkbox" };
        if (vals.every(v => typeof v === "string" && DATE_TIME.test(v)))
            return { columnType: "date", inputFormat: "YYYY-MM-DDTHH:mm:ss.SSSZ", outputFormat: "DD/MM/YYYY HH:mm" };
        if (vals.every(v => typeof v === "string" && DATE_ONLY.test(v)))
            return { columnType: "date", inputFormat: "YYYY-MM-DD", outputFormat: "DD/MM/YYYY" };
        if (vals.every(v => typeof v === "string" && /^https?:\/\//.test(v))) return { columnType: "url" };
        return { columnType: "text" };
    };
    const NUMERIC = ["number", "currency"];
    const dataColumn = (key, index) => {
        const t = infer(key);
        const col = {
            allowCellWrapping: false, allowSameOptionsInNewRow: true, alias: key,
            cellBackground: "", columnType: t.columnType,
            computedValue: `{{${w.widgetName}.processedTableData.map((currentRow, currentIndex) => ( currentRow["${String(key).replace(/"/g, '\\"')}"]))}}`,
            currencyCode: "BRL", decimals: 0, enableFilter: true, enableSort: true,
            horizontalAlignment: NUMERIC.includes(t.columnType) ? "RIGHT" : "LEFT",
            id: sanitize(key), index, isCellEditable: false, isCellVisible: true, isDerived: false,
            isDisabled: false, isDiscardVisible: true, isEditable: false, isSaveVisible: true,
            isVisible: !looksLikeId(key), label: humanize(key), notation: "standard", originalId: key,
            sticky: "", textColor: "", textSize: "0.875rem", thousandSeparator: true, validation: {},
            verticalAlignment: "CENTER", width: 150, fontStyle: "REGULAR",
        };
        if (t.inputFormat) { col.inputFormat = t.inputFormat; col.outputFormat = t.outputFormat; }
        return col;
    };

    const keysForColumns = sampleKeys.length ? sampleKeys : COLUMNS.map(c => c.id);
    const primary = {};
    let order = [];
    keysForColumns.forEach((k, i) => { const c = dataColumn(k, i); primary[c.id] = c; order.push(c.id); });
    // Keep the table's own custom (derived) columns — only the data columns are regenerated.
    const derived = { ...(w.derivedColumns || {}) };
    for (const [id, c] of Object.entries(w.primaryColumns || {})) {
        if (c && c.isDerived && !primary[id]) { primary[id] = c; order.push(id); }
    }

    const configured = [];
    for (const spec of COLUMNS) {
        const id = sanitize(spec.id);
        const c = primary[id];
        if (!c) continue;
        if (spec.label != null) c.label = spec.label;
        if (spec.width != null) c.width = spec.width;
        if (spec.columnType != null) {
            c.columnType = spec.columnType;
            if (spec.columnType === "currency" && spec.decimals == null) c.decimals = 2;
            if (NUMERIC.includes(spec.columnType) && spec.align == null) c.horizontalAlignment = "RIGHT";
        }
        if (spec.align != null) c.horizontalAlignment = spec.align;
        if (spec.hidden != null) c.isVisible = !spec.hidden;
        for (const k of ["currencyCode", "decimals", "thousandSeparator", "notation"]) if (spec[k] != null) c[k] = spec[k];
        if (spec.dateInputFormat != null) c.inputFormat = spec.dateInputFormat;
        if (spec.dateOutputFormat != null) c.outputFormat = spec.dateOutputFormat;
        configured.push(id);
    }
    const listed = COLUMNS.map(c => sanitize(c.id)).filter(id => primary[id]);
    if (HIDE_UNLISTED && listed.length) {
        for (const id of Object.keys(primary)) if (!listed.includes(id) && !primary[id].isDerived) primary[id].isVisible = false;
    }
    if (listed.length) order = [...listed, ...order.filter(id => !listed.includes(id))];
    order.forEach((id, i) => { primary[id].index = i; if (derived[id]) derived[id] = primary[id]; });

    const policy = __propertyPolicy({ widget: w, props: { tableData: binding }, replaceKeys: ["sourceData", "tableData"] });
    const notColumn = p => !/^primaryColumns\./.test(p.key);
    const bindings = policy.modify.dynamicBindingPathList.filter(notColumn);
    for (const id of Object.keys(primary)) {
        for (const [prop, v] of Object.entries(primary[id])) {
            if (typeof v === "string" && /\{\{/.test(v)) bindings.push({ key: `primaryColumns.${id}.${prop}` });
        }
    }
    const keepColumnPaths = list => (list || []).filter(p => !notColumn(p) && primary[p.key.split(".")[1]]);
    const override = {
        tableData: binding,
        primaryColumns: primary,
        columnOrder: order,
        derivedColumns: derived,
        dynamicBindingPathList: bindings,
        dynamicTriggerPathList: [...policy.modify.dynamicTriggerPathList.filter(notColumn), ...keepColumnPaths(w.dynamicTriggerPathList)],
        dynamicPropertyPathList: [...policy.modify.dynamicPropertyPathList.filter(notColumn), ...keepColumnPaths(w.dynamicPropertyPathList)],
    };
    // Same persistence as manage_table_columns: write through the layout PUT and patch the live
    // node without dispatching (a dispatch fires the table saga that resets columnOrder).
    const p = await __persistLayout({ overrides: { [WIDGET_ID]: override } });
    if (p.persisted) Object.assign(cw[WIDGET_ID], override);

    const res = { widgetId: WIDGET_ID, widgetName: w.widgetName, query: qname, tableData: binding,
        columnOrder: order, columns: order.map(id => ({ id, label: primary[id].label, columnType: primary[id].columnType, visible: primary[id].isVisible !== false })),
        configured };
    if (!keysForColumns.length) res.warning = `${qname} has no result yet, so no columns were generated — run it (execute_queries) and call connect_widget_data again, or pass columns=[{id,...}]`;
    if (p.persisted) res.persisted = true; else res.error = p.error || ("save failed: HTTP " + p.status);
    return res;
})()
