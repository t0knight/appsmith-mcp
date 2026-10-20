(async () => {
    const store = window.__store;
    const boxesIntersect = (a, b) =>
        a.leftColumn < b.rightColumn && b.leftColumn < a.rightColumn &&
        a.topRow < b.bottomRow && b.topRow < a.bottomRow;
    const out = [];
    const added = [];
    const modalsToFix = [];
    for (const spec of WIDGETS) {
        const cw = store.getState().entities.canvasWidgets || {};
        const requestedParent = spec.parent_id || "0";
        if (!cw[requestedParent]) { out.push({ error: `parent ${requestedParent} not found`, spec }); continue; }
        // Resolve the real drop target. A MODAL/CONTAINER/TABS/FORM/LIST/STATBOX widget wraps an
        // inner CANVAS_WIDGET, and children must be parented to THAT canvas — not the outer wrapper.
        // WIDGET_ADD_CHILD does NOT auto-resolve this (unlike reparent_widgets), so a child added
        // with parent_id=<modalId> lands on the wrapper and never renders (the "empty modal/card"
        // bug). Redirect to the inner canvas here, mirroring reparent_widgets. (MainContainer "0"
        // and any explicit CANVAS_WIDGET id are already canvases, so they pass through untouched;
        // for a TABS_WIDGET this picks the first tab's canvas — pass a tab's canvas id to target
        // another tab.)
        let parentId = requestedParent;
        let redirectedToInnerCanvas = null;
        if (cw[parentId].type !== "CANVAS_WIDGET") {
            const innerCanvas = Object.values(cw).find(c => c.parentId === parentId && c.type === "CANVAS_WIDGET");
            if (innerCanvas) { parentId = innerCanvas.widgetId; redirectedToInnerCanvas = parentId; }
        }
        const id = spec.new_id || ("w_" + Math.random().toString(36).slice(2, 10));
        // WIDGET_ADD_CHILD mints the widget (and, for composites, its inner CANVAS_WIDGET via
        // blueprint) synchronously into canvasWidgets; BATCH_UPDATE applies props/name. Both are
        // reflected in the store immediately, so the PUT below persists the finished widget.
        store.dispatch({
            type: "WIDGET_ADD_CHILD",
            payload: {
                widgetId: parentId, type: spec.widget_type, newWidgetId: id,
                leftColumn: spec.left, topRow: spec.top,
                columns: spec.columns, rows: spec.rows,
                parentRowSpace: 10, parentColumnSpace: 10,
                props: {},
            },
        });
        // Auto-assigned name BEFORE our rename — a modal's skeleton close/cancel buttons were
        // wired to this name, so we rewrite those refs to the new name below (item 10).
        const preName = store.getState().entities.canvasWidgets[id]?.widgetName;
        // Same property policy as update_widgets: bindings/triggers registered, JS mode set the way
        // the property pane stores it, sample select defaults dropped. Sample datasets
        // (chartData/options/sourceData) are replaced, not merged, so no sample series survives.
        const created = store.getState().entities.canvasWidgets[id];
        let applied = null;
        const modify = {};
        if (created && Object.keys(spec.props || {}).length) {
            const policy = __propertyPolicy({ widget: created, props: spec.props, replaceKeys: ["chartData", "options", "sourceData"] });
            Object.assign(modify, policy.modify);
            applied = policy.registered;
        }
        if (spec.name) modify.widgetName = spec.name;
        if (Object.keys(modify).length) {
            store.dispatch({
                type: "BATCH_UPDATE_WIDGET_PROPERTY",
                payload: { widgetId: id, updates: { modify } },
            });
        }
        const w = store.getState().entities.canvasWidgets[id];
        if (spec.widget_type === "MODAL_WIDGET" && spec.name && preName && preName !== spec.name) {
            modalsToFix.push({ id, oldName: preName, newName: spec.name });
        }
        // Surface the inner CANVAS_WIDGET id for container/tabs/form/modal so callers can parent
        // children without an extra get_widget round-trip.
        const innerCanvas = w ? Object.values(store.getState().entities.canvasWidgets)
            .find(c => c.parentId === id && c.type === "CANVAS_WIDGET") : null;
        const res = { widgetId: id, widgetName: w?.widgetName, type: w?.type, parent: w?.parentId };
        if (applied) res.applied = applied;
        if (redirectedToInnerCanvas) { res.effectiveParentId = parentId; res.redirectedToInnerCanvas = redirectedToInnerCanvas; }
        if (innerCanvas) res.innerCanvasId = innerCanvas.widgetId;
        if (w) {
            res.box = { leftColumn: w.leftColumn, topRow: w.topRow, rightColumn: w.rightColumn, bottomRow: w.bottomRow };
            // Positioning is raw grid, so a new widget silently lands on top of a sibling.
            // Report which siblings it overlaps instead of leaving it for the screenshot.
            const overlaps = Object.values(store.getState().entities.canvasWidgets)
                .filter(o => o && o.widgetId !== id && o.parentId === w.parentId
                    && o.type !== "CANVAS_WIDGET" && boxesIntersect(res.box, o))
                .map(o => o.widgetName);
            if (overlaps.length) res.overlaps = overlaps;
        }
        out.push(res);
        if (w) added.push(res);
    }

    // Rewrite modal skeleton handlers: the blueprint wires the close (X) and Cancel buttons to
    // closeModal('<auto name>'); after we rename the modal those refs dangle ("'Modal1' is not
    // defined"). Rewrite them to the new name. Blueprint children may land a tick later, so poll
    // briefly for them; the final __persistLayout rebuilds the DSL from the store, so mutating
    // the children via BATCH_UPDATE here is enough to persist.
    const descendantsOf = rootId => {
        const all = store.getState().entities.canvasWidgets || {};
        const acc = []; const stack = [rootId];
        while (stack.length) {
            const pid = stack.pop();
            for (const c of Object.values(all)) if (c.parentId === pid) { acc.push(c); stack.push(c.widgetId); }
        }
        return acc;
    };
    const refSrc = m => `(closeModal|showModal)\\((['"])${m.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\2\\)`;
    for (const m of modalsToFix) {
        const src = refSrc(m.oldName);
        // Separate regexes: a plain one for .test() (a /g regex is stateful across test calls),
        // a global one for .replace().
        const reTest = new RegExp(src);
        const reAll = new RegExp(src, "g");
        const start = Date.now();
        let rewritten = 0;
        // Wait until a descendant actually references the old name (skeleton buttons rendered).
        while (Date.now() - start < 1500) {
            const kids = descendantsOf(m.id);
            const hit = kids.some(k => Object.values(k).some(v => typeof v === "string" && reTest.test(v)));
            if (hit) break;
            await new Promise(r => setTimeout(r, 100));
        }
        for (const k of descendantsOf(m.id)) {
            const patch = {};
            for (const [prop, val] of Object.entries(k)) {
                if (typeof val === "string" && reTest.test(val)) {
                    patch[prop] = val.replace(reAll, `$1($2${m.newName}$2)`);
                }
            }
            if (Object.keys(patch).length) {
                store.dispatch({ type: "BATCH_UPDATE_WIDGET_PROPERTY", payload: { widgetId: k.widgetId, updates: { modify: patch } } });
                rewritten += Object.keys(patch).length;
            }
        }
        const res = out.find(r => r.widgetId === m.id);
        if (res) res.rewroteModalRefs = rewritten;
    }

    if (added.length) {
        const p = await __persistLayout({});
        for (const r of added) {
            if (p.persisted) r.persisted = true;
            else r.error = p.error || ("save failed: HTTP " + p.status);
        }
    }
    return out;
})()
