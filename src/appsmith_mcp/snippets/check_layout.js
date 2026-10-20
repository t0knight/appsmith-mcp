(async () => {
    const store = window.__store;

    // ── 1. Settle ────────────────────────────────────────────────────────────────────────
    // Right after a refresh/navigation the page shows loading skeletons and queries are still
    // in flight, so a widget legitimately missing from the DOM would look "broken". Wait for
    // in-flight queries to finish (bounded) before measuring, and report what's still pending.
    const pendingQueries = () => (store.getState().entities.actions || [])
        .filter(a => a && a.isLoading)
        .map(a => a.config && a.config.name)
        .filter(Boolean);
    const start = Date.now();
    let pending = pendingQueries();
    while (pending.length && Date.now() - start < 4000) {
        await new Promise(r => setTimeout(r, 150));
        pending = pendingQueries();
    }
    const settled = pending.length === 0;

    const cw = store.getState().entities.canvasWidgets || {};
    const evalTree = store.getState().evaluations?.tree || {};

    // ── 2. Expected-vs-problem classification for widgets missing from the DOM ────────────
    // Appsmith deliberately doesn't render descendants of a closed modal, of a non-active tab,
    // or of an isVisible:false container. Those missing widgets are EXPECTED, not defects —
    // classifying them keeps the real problems from drowning (a page can have dozens of modal/
    // tab children legitimately absent).
    const ancestors = w => {
        const chain = [];
        let p = cw[w.parentId];
        const seen = new Set();
        while (p && !seen.has(p.widgetId)) { seen.add(p.widgetId); chain.push(p); p = cw[p.parentId]; }
        return chain;
    };
    const TABS_RE = /TABS_WIDGET/;
    // The canvas id of a tabs widget's currently-selected tab.
    const activeTabCanvas = tabs => {
        const selected = evalTree[tabs.widgetName] && evalTree[tabs.widgetName].selectedTab;
        const arr = Object.values(tabs.tabsObj || {});
        const tab = arr.find(t => t.label === selected) || arr.find(t => t.isVisible !== false) || arr[0];
        return tab ? tab.widgetId : null; // in TABS_WIDGET_V2 a tab's widgetId IS its canvas id
    };
    const classifyMissing = w => {
        if (w.isVisible === false) return "hidden (isVisible:false)";
        for (const a of ancestors(w)) {
            if (a.type === "MODAL_WIDGET") return `inside modal ${a.widgetName} (closed)`;
            if (a.isVisible === false) return `inside hidden container ${a.widgetName} (isVisible:false)`;
            if (a.type === "CANVAS_WIDGET") {
                const tabs = cw[a.parentId];
                if (tabs && TABS_RE.test(tabs.type)) {
                    const active = activeTabCanvas(tabs);
                    if (active && active !== a.widgetId) return `inside inactive tab of ${tabs.widgetName}`;
                }
            }
        }
        return null; // genuinely absent for no legitimate reason → a real problem
    };

    // ── 3. Grid-overlap detection (unchanged) ─────────────────────────────────────────────
    // Overlay widgets (modals) render as absolutely-positioned popovers, hidden until
    // triggered, so their grid box legitimately covers MainContainer children — exclude them.
    const OVERLAY_TYPES = new Set(["MODAL_WIDGET"]);
    const siblingsByParent = {};
    for (const w of Object.values(cw)) {
        if (w.type === "CANVAS_WIDGET" || OVERLAY_TYPES.has(w.type)) continue;
        (siblingsByParent[w.parentId] = siblingsByParent[w.parentId] || []).push(w);
    }
    const intersects = (a, b) =>
        a.leftColumn < b.rightColumn && b.leftColumn < a.rightColumn &&
        a.topRow < b.bottomRow && b.topRow < a.bottomRow;

    const widgets = [];
    for (const w of Object.values(cw)) {
        if (w.type === "CANVAS_WIDGET") continue;

        const siblings = (siblingsByParent[w.parentId] || []).filter(s => s.widgetId !== w.widgetId);
        const overlaps = OVERLAY_TYPES.has(w.type)
            ? []
            : siblings.filter(s => intersects(w, s)).map(s => ({ id: s.widgetId, name: s.widgetName }));

        const entry = {
            id: w.widgetId, name: w.widgetName, type: w.type, parentId: w.parentId,
            grid: { left: w.leftColumn, top: w.topRow, right: w.rightColumn, bottom: w.bottomRow },
            overlaps,
        };

        const dom = document.querySelector(`.appsmith_widget_${w.widgetId}`);
        if (!dom) {
            entry.rendered = false;
            const reason = classifyMissing(w);
            if (reason) { entry.status = "expected"; entry.expectedReason = reason; }
            else { entry.status = "problem"; entry.detail = "not in the DOM and not inside a closed modal / inactive tab / hidden container"; }
            widgets.push(entry);
            continue;
        }
        entry.rendered = true;
        const rect = dom.getBoundingClientRect();
        entry.box = { width: Math.round(rect.width), height: Math.round(rect.height) };
        const scrollH = dom.scrollHeight;
        entry.overflowsContainer = scrollH > dom.clientHeight + 1;
        entry.scrollHeight = scrollH;

        const iframe = dom.querySelector("iframe");
        if (iframe) {
            let contentHeight = null, iframeContentOverflows = null;
            try {
                const body = iframe.contentDocument && iframe.contentDocument.body;
                if (body) {
                    contentHeight = body.scrollHeight;
                    iframeContentOverflows = body.scrollHeight > iframe.offsetHeight + 1;
                }
            } catch (e) { /* cross-origin */ }
            entry.iframe = { width: iframe.offsetWidth, height: iframe.offsetHeight, contentHeight, overflows: iframeContentOverflows };
        } else {
            entry.iframe = null;
        }
        entry.status = (overlaps.length || entry.overflowsContainer) ? "problem" : "ok";
        if (overlaps.length) entry.detail = "grid rectangle overlaps a sibling";
        else if (entry.overflowsContainer) entry.detail = "rendered content overflows its container";
        widgets.push(entry);
    }

    // ── 4. Composition: rows on the same top, and vertical gaps between blocks ─────────────
    // set_widget_bounds echoes the requested top, not the effective one after relayout, so a
    // stray widget pushed to a different row is invisible in the tool result. Surface, per
    // parent, which widgets share a top and where empty vertical bands sit (a gap between two
    // blocks that looks intentional but usually isn't).
    const GAP_ROWS = 4; // >= 4 grid rows (~40px) is a visible gap worth flagging
    const layoutByParent = [];
    for (const [pid, kidsRaw] of Object.entries(siblingsByParent)) {
        const kids = kidsRaw.slice().sort((a, b) => a.topRow - b.topRow || a.leftColumn - b.leftColumn);
        if (!kids.length) continue;
        const parent = cw[pid];
        const rowMap = {};
        for (const k of kids) (rowMap[k.topRow] = rowMap[k.topRow] || []).push(k.widgetName);
        const rows = Object.keys(rowMap).map(Number).sort((a, b) => a - b)
            .map(top => ({ top, widgets: rowMap[top] }));

        const intervals = kids.map(k => [k.topRow, k.bottomRow]).sort((a, b) => a[0] - b[0]);
        const gaps = [];
        if (intervals[0][0] >= GAP_ROWS) gaps.push({ fromRow: 0, toRow: intervals[0][0], rows: intervals[0][0] });
        let cursor = intervals[0][1];
        for (const [t, b] of intervals) {
            if (t - cursor >= GAP_ROWS) gaps.push({ fromRow: cursor, toRow: t, rows: t - cursor });
            cursor = Math.max(cursor, b);
        }
        layoutByParent.push({
            parentId: pid,
            parentName: parent && parent.widgetName,
            rows,
            gaps,
        });
    }

    const problems = widgets.filter(e => e.status === "problem");
    return { settled, pendingQueries: pending, problemCount: problems.length, problems, widgets, layoutByParent };
})()
