(() => {
    const cw = window.__store.getState().entities.canvasWidgets || {};
    const out = [];
    for (const w of Object.values(cw)) {
        if (w.type === "CANVAS_WIDGET") continue;
        const dom = document.querySelector(`.appsmith_widget_${w.widgetId}`);
        if (!dom) continue;
        const rect = dom.getBoundingClientRect();
        const box = { width: Math.round(rect.width), height: Math.round(rect.height) };

        // Outer overflow: does the widget's rendered content exceed its container?
        const scrollH = dom.scrollHeight;
        const clientH = dom.clientHeight;
        const overflowsContainer = scrollH > clientH + 1;

        // For widgets with iframes (Custom, IFrame, DocumentViewer), peek inside if same-origin.
        let contentHeight = null;
        let iframeContentOverflows = null;
        const iframe = dom.querySelector("iframe");
        if (iframe) {
            try {
                const body = iframe.contentDocument && iframe.contentDocument.body;
                if (body) {
                    contentHeight = body.scrollHeight;
                    iframeContentOverflows = body.scrollHeight > iframe.offsetHeight + 1;
                }
            } catch (e) {
                // cross-origin
            }
        }

        out.push({
            id: w.widgetId, name: w.widgetName, type: w.type,
            grid: { left: w.leftColumn, top: w.topRow, right: w.rightColumn, bottom: w.bottomRow },
            box,
            overflowsContainer,
            scrollHeight: scrollH,
            iframe: iframe ? { width: iframe.offsetWidth, height: iframe.offsetHeight, contentHeight, overflows: iframeContentOverflows } : null,
        });
    }
    return out;
})()
