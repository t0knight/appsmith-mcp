(() => {
    // Generate the resetWidget(...) calls for every stateful descendant of a container/modal, so a
    // close/cancel/search handler can clear the whole subtree without hand-listing widgets (and
    // silently forgetting one). Returns the ready-to-paste JS plus the widget list.
    const cw = window.__store.getState().entities.canvasWidgets || {};
    // Accept an id or a widget name.
    let root = cw[CONTAINER_ID];
    if (!root) root = Object.values(cw).find(w => w && w.widgetName === CONTAINER_ID);
    if (!root) return { error: `container '${CONTAINER_ID}' not found (by id or name)` };

    // Widgets that hold user state resetWidget actually clears.
    const RESETTABLE = /(INPUT|SELECT|CHECKBOX|SWITCH|RADIO|DATE_PICKER|CURRENCY|PHONE|MULTI|SLIDER|RATE|RICH_TEXT|FILE_PICKER|AUDIO_RECORDER|CATEGORY|RANGE|CODE_SCANNER)/;

    const descendants = rootId => {
        const acc = []; const stack = [rootId];
        while (stack.length) {
            const pid = stack.pop();
            for (const c of Object.values(cw)) if (c.parentId === pid) { acc.push(c); stack.push(c.widgetId); }
        }
        return acc;
    };

    const widgets = descendants(root.widgetId)
        .filter(w => RESETTABLE.test(w.type))
        .sort((a, b) => (a.topRow - b.topRow) || (a.leftColumn - b.leftColumn))
        .map(w => w.widgetName);

    const isModal = root.type === "MODAL_WIDGET";
    const lines = widgets.map(n => `resetWidget('${n}');`);
    // For a modal, the handler usually also closes it.
    if (isModal) lines.push(`closeModal('${root.widgetName}');`);
    return { container: root.widgetName, containerType: root.type, isModal, widgets, count: widgets.length, js: lines.join(" ") };
})()
