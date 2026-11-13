(async () => {
    const store = window.__store;
    const pendingQueries = () =>
        (store.getState().entities.actions || [])
            .filter(a => a && a.isLoading)
            .map(a => a.config && a.config.name)
            .filter(Boolean);
    const skeletonCount = () =>
        document.querySelectorAll(".bp3-skeleton, .t--widget-skeleton, [class*='skeleton']").length;
    const hasArtboard = () =>
        !!document.querySelector(".t--canvas-artboard, [data-testid='t--canvas-artboard']");

    // Called right after refresh_page, this used to measure the loading skeleton and report
    // every table as broken. Wait for the page to settle first: no query in flight, no
    // skeleton cells, artboard present. Bounded — a genuinely stuck query still returns, with
    // settled:false and the query named, so the caller knows to wait rather than to "fix" it.
    let settled = false;
    for (let i = 0; i < 24; i++) {
        if (hasArtboard() && pendingQueries().length === 0 && skeletonCount() === 0) {
            settled = true;
            break;
        }
        await new Promise(r => setTimeout(r, 250));
    }

    const s = store.getState();
    const cw = s.entities.canvasWidgets || {};
    const pid = s.entities.pageList.currentPageId;
    const page = (s.entities.pageList.pages || []).find(p => p.pageId === pid);
    const artboard = document.querySelector(".t--canvas-artboard, [data-testid='t--canvas-artboard']");

    // Why a widget is legitimately absent from the DOM: inside a closed modal, inside an
    // inactive tab, or under an isVisible:false ancestor. Appsmith renders none of these by
    // design, so listing them as defects buries the one real problem. Returns a human reason
    // or null.
    const hiddenReason = (w) => {
        let cur = w;
        const seen = new Set();
        while (cur && !seen.has(cur.widgetId)) {
            seen.add(cur.widgetId);
            if (cur.isVisible === false) {
                return cur === w ? "isVisible is false" : `inside '${cur.widgetName}', whose isVisible is false`;
            }
            const parent = cur.parentId ? cw[cur.parentId] : null;
            if (!parent) break;
            if (parent.type === "MODAL_WIDGET") {
                return `inside modal '${parent.widgetName}', which is closed`;
            }
            if (parent.type === "TABS_WIDGET") {
                const tabEl = document.querySelector(`.appsmith_widget_${cur.widgetId}`);
                if (!tabEl) return `inside an inactive tab of '${parent.widgetName}'`;
            }
            cur = parent;
        }
        if (w.type === "MODAL_WIDGET") return "modal is closed (opens on demand)";
        return null;
    };

    const problems = [];
    const expected = [];
    const widgets = Object.values(cw).filter(w => w.type !== "CANVAS_WIDGET");
    let rendered = 0;

    for (const w of widgets) {
        const el = document.querySelector(`.appsmith_widget_${w.widgetId}`);
        if (!el) {
            const reason = hiddenReason(w);
            const entry = {
                id: w.widgetId, name: w.widgetName, type: w.type, issue: "missingFromDom",
                detail: reason || "present in the DSL but no node in the DOM — the widget failed to render",
            };
            if (reason) { entry.expected = true; expected.push(entry); }
            else problems.push(entry);
            continue;
        }
        rendered++;
        const rect = el.getBoundingClientRect();
        if (rect.width < 1 || rect.height < 1) {
            problems.push({
                id: w.widgetId, name: w.widgetName, type: w.type, issue: "zeroSize",
                detail: `rendered at ${Math.round(rect.width)}x${Math.round(rect.height)}px`,
            });
            continue;
        }

        // A table with columns configured but no header cells means primaryColumns is
        // malformed — Appsmith renders nothing and logs nothing for this.
        if (w.type === "TABLE_WIDGET_V2") {
            // A computedValue whose empty-table fallback is a bare identifier throws
            // `ReferenceError: <id> is not defined` per column while the table is empty —
            // a phantom bug that disappears when data arrives. Appsmith's own column
            // auto-generator produces this shape; detect and name it.
            for (const [cid, col] of Object.entries(w.primaryColumns || {})) {
                const cv = col && col.computedValue;
                if (typeof cv !== "string") continue;
                const m = cv.match(/:\s*([A-Za-z_$][\w$]*)\s*\}\)\(\)\s*\}\}\s*$/);
                if (m && !["null", "undefined", "true", "false"].includes(m[1])) {
                    problems.push({
                        id: w.widgetId, name: w.widgetName, type: w.type, issue: "tableColumnFallback",
                        detail: `column '${cid}' computedValue falls back to bare identifier `
                              + `'${m[1]}' — throws ReferenceError while the table is empty; `
                              + `the fallback should be [] (rebuild with manage_table_columns)`,
                    });
                }
            }
            const configured = Object.keys(w.primaryColumns || {}).length;
            const headers = el.querySelectorAll(".thead .th, [role='columnheader'], th").length;
            if (configured > 0 && headers === 0) {
                problems.push({
                    id: w.widgetId, name: w.widgetName, type: w.type, issue: "columnsNotRendered",
                    detail: `${configured} column(s) in primaryColumns but 0 header cells rendered — `
                          + `the column objects are malformed; rebuild them with manage_table_columns`,
                });
                continue;
            }
            if (configured === 0) {
                problems.push({
                    id: w.widgetId, name: w.widgetName, type: w.type, issue: "noColumns",
                    detail: "no primaryColumns yet — bind tableData and run the query first",
                });
                continue;
            }
        }

        const hasContent = el.innerText.trim().length > 0
            || el.querySelectorAll("img,svg,canvas,iframe,input,button,table,select,textarea").length > 0;
        if (!hasContent) {
            problems.push({
                id: w.widgetId, name: w.widgetName, type: w.type, issue: "emptyRender",
                detail: "node exists and has size but renders no visible content",
            });
        }
    }

    // Evaluation errors, with the text — this is what tells you *why* a widget is blank.
    const evalErrors = [];
    for (const e of Object.values(s.ui.debugger.errors || {})) {
        evalErrors.push({
            severity: e.severity,
            source: e.source && e.source.name,
            propertyPath: e.source && e.source.propertyPath,
            messages: (e.messages || []).map(m => m && (m.message || m.originalMessage)).filter(Boolean),
        });
    }

    return {
        page: page && page.pageName,
        canvasRendered: !!artboard,
        settled,
        pendingQueries: pendingQueries(),
        widgetsInDsl: widgets.length,
        widgetsRendered: rendered,
        blankPage: widgets.length > 0 && rendered === 0,
        problems,
        expected,
        evalErrors,
    };
})()
