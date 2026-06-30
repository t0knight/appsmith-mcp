(() => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    const w = cw[WIDGET_ID];
    if (!w) return { error: `widget ${WIDGET_ID} not found` };
    if (w.type !== "TABS_WIDGET") return { error: `widget is ${w.type}, not TABS_WIDGET` };

    const result = { added: [], removed: [], reordered: false };

    if (Array.isArray(REMOVE) && REMOVE.length) {
        const tabs = w.tabsObj || {};
        for (const tabId of REMOVE) {
            const t = tabs[tabId];
            if (!t) continue;
            window.__store.dispatch({
                type: "WIDGET_DELETE_TAB_CHILD",
                payload: { id: t.id, index: t.index, isVisible: t.isVisible, label: t.label, widgetId: WIDGET_ID },
            });
            result.removed.push(tabId);
        }
    }

    if (Array.isArray(ADD) && ADD.length) {
        for (const tab of ADD) {
            // The saga generates the id, label, and child Canvas. Capture which tab is new
            // by snapshotting before/after.
            const before = new Set(Object.keys((window.__store.getState().entities.canvasWidgets[WIDGET_ID] || {}).tabsObj || {}));
            window.__store.dispatch({ type: "WIDGET_ADD_NEW_TAB_CHILD", payload: { widgetId: WIDGET_ID } });
            const after = (window.__store.getState().entities.canvasWidgets[WIDGET_ID] || {}).tabsObj || {};
            const newId = Object.keys(after).find(id => !before.has(id));
            if (newId && tab.label) {
                const updated = { ...after, [newId]: { ...after[newId], label: tab.label } };
                window.__store.dispatch({
                    type: "BATCH_UPDATE_WIDGET_PROPERTY",
                    payload: { widgetId: WIDGET_ID, updates: { modify: { tabsObj: updated } } },
                });
            }
            result.added.push({ id: newId, label: tab.label || (after[newId] && after[newId].label) });
        }
    }

    if (Array.isArray(REORDER) && REORDER.length) {
        const current = (window.__store.getState().entities.canvasWidgets[WIDGET_ID] || {}).tabsObj || {};
        const next = { ...current };
        REORDER.forEach((tabId, idx) => { if (next[tabId]) next[tabId] = { ...next[tabId], index: idx }; });
        // Anyone not in REORDER goes after, preserving original order
        const seen = new Set(REORDER);
        let nextIdx = REORDER.length;
        for (const id of Object.keys(next)) {
            if (!seen.has(id)) next[id] = { ...next[id], index: nextIdx++ };
        }
        window.__store.dispatch({
            type: "BATCH_UPDATE_WIDGET_PROPERTY",
            payload: { widgetId: WIDGET_ID, updates: { modify: { tabsObj: next } } },
        });
        result.reordered = true;
    }

    const final = (window.__store.getState().entities.canvasWidgets[WIDGET_ID] || {}).tabsObj || {};
    return {
        widgetId: WIDGET_ID,
        tabs: Object.values(final).sort((a, b) => a.index - b.index).map(t => ({ id: t.id, label: t.label, widgetId: t.widgetId, index: t.index })),
        ...result,
    };
})()
