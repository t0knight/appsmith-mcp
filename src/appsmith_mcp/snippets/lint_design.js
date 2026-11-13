(() => {
    // Design lint: answers "does it look good?" the way get_render_health answers "is it broken?".
    // Pure read + rules — every finding here is something a human reviewer would otherwise send back.
    const store = window.__store;
    const cw = store.getState().entities.canvasWidgets || {};
    const actions = (store.getState().entities.actions || []).map(a => a.config && a.config.name).filter(Boolean);
    const theme = store.getState().ui.appTheming?.selectedTheme?.properties || {};
    const themeColors = Object.values(theme.colors || {}).map(String);

    const ancestors = w => {
        const chain = []; let p = cw[w.parentId]; const seen = new Set();
        while (p && !seen.has(p.widgetId)) { seen.add(p.widgetId); chain.push(p); p = cw[p.parentId]; }
        return chain;
    };
    const insideModal = w => ancestors(w).some(a => a.type === "MODAL_WIDGET");

    const LABELED = /^(INPUT_WIDGET_V2|SELECT_WIDGET|MULTI_SELECT_WIDGET_V2|MULTI_SELECT_TREE_WIDGET|SINGLE_SELECT_TREE_WIDGET|DATE_PICKER_WIDGET2|CURRENCY_INPUT_WIDGET|PHONE_INPUT_WIDGET|RADIO_GROUP_WIDGET|CHECKBOX_GROUP_WIDGET|SWITCH_GROUP_WIDGET|NUMBER_SLIDER_WIDGET|RANGE_SLIDER_WIDGET|CATEGORY_SLIDER_WIDGET)$/;
    const INTERACTIVE = /(INPUT|SELECT|BUTTON|CHECKBOX|SWITCH|RADIO|DATE_PICKER|SLIDER|FILE_PICKER|RATE)/;
    const COLOR_PROPS = ["accentColor", "borderColor", "backgroundColor", "cellBackground", "textColor", "headerRowColor", "headerTextColor", "buttonColor"];
    const isHex = v => typeof v === "string" && /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(v.trim());
    const isThemeBinding = v => typeof v === "string" && /\{\{\s*appsmith\.theme/.test(v);

    // type -> { prop: controlType } for JS-convertible props with a visual control (from server.py).
    const UI_CONTROLS = /*__UI_CONTROLS__*/{};
    const simpleQueryData = /^\{\{[^.]*\.data\}\}$/;  // what the Data dropdown can display
    const themeBinding = /^\{\{\s*appsmith\.theme\.[^{}]*\}\}$/;
    const DATA_PROPS = { TABLE_WIDGET_V2: "tableData", SELECT_WIDGET: "sourceData", MULTI_SELECT_WIDGET_V2: "sourceData" };
    const DEFAULT_NAME = /^[A-Z][A-Za-z]*\d+$/;  // Button1, Table3, IconButton1 — never renamed

    const findings = [];
    const add = (rule, severity, w, detail, extra) => findings.push({ rule, severity, widget: w.widgetName, id: w.widgetId, type: w.type, detail, ...(extra || {}) });

    for (const w of Object.values(cw)) {
        if (w.type === "CANVAS_WIDGET") continue;

        // 1. Labelled input without a real label — empty, or still the untouched default "Label"
        // (INPUT_WIDGET_V2 renders `label`; if the MCP set `labelText` but left `label` default,
        // the screen shows "Label" even though labelText looks right — feedback 3.5).
        if (LABELED.test(w.type)) {
            const label = w.label != null ? w.label : w.labelText;
            if (!label || String(label).trim() === "") add("input_without_label", "warn", w, "labelled input has an empty label");
            else if (String(label).trim() === "Label") add("input_without_label", "warn", w, 'input still shows the default "Label" — set its real label');
        }

        // 2. Interactive widget without a tooltip.
        if (INTERACTIVE.test(w.type) && (!w.tooltip || String(w.tooltip).trim() === "")) {
            add("interactive_without_tooltip", "info", w, "no tooltip — consider a help hint");
        }

        // 3. Button without an icon.
        if (/^(BUTTON_WIDGET|ICON_BUTTON_WIDGET)$/.test(w.type) && (!w.iconName || w.iconName === "(none)")) {
            add("button_without_icon", "info", w, "button has no iconName");
        }

        // 4. Hardcoded color where a theme token exists.
        for (const p of COLOR_PROPS) {
            const v = w[p];
            if (isHex(v) && !isThemeBinding(v) && themeColors.length) {
                add("hardcoded_color", "info", w, `${p}=${v} is a raw hex; bind to a theme token`, { property: p });
            }
        }

        // 8. A binding on a property whose pane shows a visual control (switch/dropdown/colour/data
        // selector) without JS mode — the maintainer sees an empty/wrong field instead of the code.
        const controls = UI_CONTROLS[w.type] || {};
        const jsMode = new Set((w.dynamicPropertyPathList || []).map(p => p.key));
        for (const [prop, control] of Object.entries(controls)) {
            const v = w[prop];
            if (typeof v !== "string" || !/\{\{/.test(v) || jsMode.has(prop) || themeBinding.test(v)) continue;
            if (control === "ONE_CLICK_BINDING_CONTROL" && simpleQueryData.test(v)) continue;
            add("binding_hidden_in_ui", "warn", w, `${prop} has a binding but the property pane shows the ${control} control, not the code — set it through update_widgets/connect_widget_data (use {{query.data}} without spaces for data)`, { property: prop });
        }

        // 9. Data fed through a transforming expression instead of the query itself.
        const dataProp = DATA_PROPS[w.type];
        const dataVal = dataProp && w[dataProp];
        if (typeof dataVal === "string" && /\{\{/.test(dataVal) && !simpleQueryData.test(dataVal)
            && actions.some(a => new RegExp(`\\b${a}\\.data\\b`).test(dataVal))) {
            add("data_transformed_in_binding", "info", w, `${dataProp} transforms query data inline — move the shaping into the query and connect it with connect_widget_data so the Data dropdown shows the query`, { property: dataProp });
        }

        // 10. Widget still carries its auto-generated name.
        if (DEFAULT_NAME.test(w.widgetName || "")) {
            add("default_widget_name", "warn", w, `rename ${w.widgetName} following the page prefixes (bt_, tb_, sel_, inp_, md_, cn_, txt_...)`);
        }

        // 6. Modal descendant bound directly to <query>.data — reopening shows stale data.
        if (insideModal(w)) {
            for (const pth of (w.dynamicBindingPathList || [])) {
                const val = pth.key.split(".").reduce((o, k) => (o == null ? o : o[k.split("[")[0]]), w);
                const raw = typeof val === "string" ? val : "";
                const hit = actions.find(a => new RegExp(`\\b${a}\\.data\\b`).test(raw));
                if (hit) { add("modal_binds_query_data", "info", w, `binds ${pth.key} to ${hit}.data — refresh it when the modal opens (e.g. {{ ${hit}.run().then(() => showModal('<modal>')) }}) so reopening never shows the previous record`, { property: pth.key, query: hit }); break; }
            }
        }

        // 5/7. Table columns: label == raw column id, or a broken empty-table fallback.
        if (w.type === "TABLE_WIDGET_V2" && w.primaryColumns) {
            for (const [cid, col] of Object.entries(w.primaryColumns)) {
                if (col && col.isVisible !== false && (col.label == null || col.label === col.originalId || col.label === cid)) {
                    add("table_raw_column_label", "info", w, `column "${cid}" shows its raw query name as the header`, { column: cid });
                }
                // 12. Id-like data column left visible.
                const rawName = (col && (col.originalId || col.alias)) || cid;
                if (col && col.isVisible !== false && /(^id(_|$)|_id$|Id$)/.test(rawName)) {
                    add("table_visible_id_column", "info", w, `column "${cid}" looks like an id and is visible — hide it with manage_table_columns(configure=[{id, hidden:true}]) unless the user needs it`, { column: cid });
                }
                for (const p of COLOR_PROPS) {
                    const v = col && col[p];
                    if (isHex(v) && themeColors.length) {
                        add("hardcoded_color", "info", w, `column "${cid}".${p}=${v} is a raw hex; bind to a theme token`, { column: cid, property: p });
                    }
                }
                const cv = col && col.computedValue;
                if (typeof cv === "string" && /:\s*[A-Za-z_$][\w$]*\s*\}\)\(\)\s*\}\}/.test(cv)) {
                    add("table_bad_fallback", "warn", w, `column "${cid}" computedValue has a bare-identifier empty-table fallback (throws ReferenceError when empty); use ": []"`, { column: cid });
                }
            }
        }
    }

    // 13/14. Geometry per parent canvas: row-mates pushed to different rows, and empty bands.
    const byParent = {};
    for (const w of Object.values(cw)) {
        if (w.type === "CANVAS_WIDGET" || w.type === "MODAL_WIDGET" || w.widgetId === "0") continue;
        (byParent[w.parentId] = byParent[w.parentId] || []).push(w);
    }
    for (const kids of Object.values(byParent)) {
        // Two widgets side by side (disjoint, adjacent columns), of similar height, whose vertical
        // ranges overlap but whose tops differ — they were meant to share a row and one got pushed.
        const flagged = new Set();
        for (let i = 0; i < kids.length; i++) {
            for (let j = i + 1; j < kids.length; j++) {
                const a = kids[i], b = kids[j];
                const disjointCols = a.rightColumn <= b.leftColumn || b.rightColumn <= a.leftColumn;
                const near = Math.min(Math.abs(a.rightColumn - b.leftColumn), Math.abs(b.rightColumn - a.leftColumn)) <= 4;
                const vOverlap = a.topRow < b.bottomRow && b.topRow < a.bottomRow;
                const similarH = Math.abs((a.bottomRow - a.topRow) - (b.bottomRow - b.topRow)) <= 1;
                if (disjointCols && near && vOverlap && similarH && a.topRow !== b.topRow) {
                    const lower = a.topRow > b.topRow ? a : b;
                    const other = lower === a ? b : a;
                    if (!flagged.has(lower.widgetId)) {
                        flagged.add(lower.widgetId);
                        add("row_misaligned", "warn", lower, `starts on row ${lower.topRow} while its row-mate ${other.widgetName} starts on ${other.topRow} — set_widget_bounds(top: ${other.topRow})`);
                    }
                }
            }
        }
        const sorted = [...kids].sort((x, y) => x.topRow - y.topRow);
        let maxBottom = null;
        for (const w of sorted) {
            if (maxBottom != null && w.topRow - maxBottom >= 6) {
                add("vertical_gap", "info", w, `empty band of ${w.topRow - maxBottom} rows above ${w.widgetName} in its container — close it with set_widget_bounds`);
            }
            maxBottom = maxBottom == null ? w.bottomRow : Math.max(maxBottom, w.bottomRow);
        }
    }

    // 11. Queries / JS functions left on AUTOMATIC: they re-run on every dependency change (and on
    // load). Only keep that when the reactivity is intended — otherwise MANUAL or ON_PAGE_LOAD.
    const autoHit = (name, id, kind) => findings.push({ rule: "automatic_run_behaviour", severity: "warn", widget: name, id, type: kind,
        detail: `${name} runs AUTOMATIC — set MANUAL (call it from the event) or ON_PAGE_LOAD with set_run_behaviour unless it must react to every change` });
    for (const a of (store.getState().entities.actions || [])) {
        if (a.config && a.config.runBehaviour === "AUTOMATIC") autoHit(a.config.name, a.config.id, "QUERY");
    }
    for (const c of (store.getState().entities.jsActions || [])) {
        for (const f of ((c.config && c.config.actions) || [])) {
            if (f.runBehaviour === "AUTOMATIC") autoHit(`${c.config.name}.${f.name}`, f.id, "JS_FUNCTION");
        }
    }

    const bySeverity = { warn: findings.filter(f => f.severity === "warn"), info: findings.filter(f => f.severity === "info") };
    return { count: findings.length, warnCount: bySeverity.warn.length, findings };
})()
