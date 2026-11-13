(async () => {
    const store = window.__store;
    const find = id => (store.getState().entities.actions || []).find(a => a.config && a.config.id === id);

    const shrink = (body) => {
        if (!Array.isArray(body)) return { body, rowCount: null, truncated: false };
        if (MAX_ROWS < 0 || body.length <= MAX_ROWS) return { body, rowCount: body.length, truncated: false };
        return { body: body.slice(0, MAX_ROWS), rowCount: body.length, truncated: true };
    };

    const out = [];
    for (const id of ACTION_IDS) {
        const before = find(id);
        if (!before) { out.push({ id, error: "query not found on the current page" }); continue; }
        const prevData = before.data;

        // The Run button's own saga. It evaluates the {{...}} bindings in the action
        // config against the current page state and substitutes them as bound parameters
        // before sending — which is why a raw POST to /api/v1/actions/execute fails with
        // "Incorrect syntax near '{'" on any query that uses a binding.
        store.dispatch({
            type: "RUN_ACTION_REQUEST",
            payload: { id, actionId: id, skipOpeningDebugger: true },
        });

        const deadline = Date.now() + TIMEOUT_MS;
        let sawLoading = false, settled = null;
        while (Date.now() < deadline) {
            await new Promise(r => setTimeout(r, 250));
            const cur = find(id);
            if (!cur) break;
            if (cur.isLoading) { sawLoading = true; continue; }
            if (sawLoading || cur.data !== prevData) { settled = cur; break; }
        }

        const cur = settled || find(id);
        const d = cur && cur.data;
        if (!d) {
            out.push({ id, name: cur && cur.config.name, ok: false, timedOut: !settled,
                       error: "no response captured before the timeout" });
            continue;
        }
        const { body, rowCount, truncated } = shrink(d.body);
        const entry = {
            id,
            name: cur.config.name,
            ok: !!d.isExecutionSuccess,
            isExecutionSuccess: d.isExecutionSuccess,
            statusCode: d.statusCode,
            rowCount,
            truncated,
            body,
        };
        if (!d.isExecutionSuccess) {
            const pd = d.pluginErrorDetails || {};
            entry.error = pd.downstreamErrorMessage || pd.appsmithErrorMessage || d.readableError || "query failed";
            entry.errorTitle = pd.title;
        }
        if (!settled) entry.timedOut = true;
        out.push(entry);
    }
    return out;
})()
