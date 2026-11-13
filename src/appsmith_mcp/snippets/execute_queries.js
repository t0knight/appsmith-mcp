(async () => {
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    const store = window.__store;
    // Before running, wait (bounded) for the eval worker's copy of appsmith.store to catch up with
    // the main-thread store. set_store / a session-token refresh writes the main-thread store
    // synchronously, but the worker reprocesses it asynchronously (~300ms) — fire a query too soon
    // and a header binding like {{appsmith.store.supabase_token}} resolves against the OLD value
    // (feedback 3.2: 401 right after refreshing a Supabase session token). Comparing the two copies
    // and waiting until they match closes that desync window.
    let evalSynced = null;
    if (AWAIT_EVAL) {
        // Compare key-by-key (NOT raw JSON.stringify of the whole object): the eval tree can rebuild
        // the store with a different top-level key order, which would make a stringify compare never
        // match and always burn the full timeout + warn spuriously.
        const eq = (a, b) => {
            a = a || {}; b = b || {};
            const ak = Object.keys(a);
            if (ak.length !== Object.keys(b).length) return false;
            for (const k of ak) { if (JSON.stringify(a[k]) !== JSON.stringify(b[k])) return false; }
            return true;
        };
        const truth = () => store.getState().entities?.app?.store || {};
        const seen = () => store.getState().evaluations?.tree?.appsmith?.store || {};
        const start = Date.now();
        while (Date.now() - start < 4000 && !eq(truth(), seen())) {
            await new Promise(r => setTimeout(r, 100));
        }
        evalSynced = eq(truth(), seen());
    }
    const out = [];
    for (const id of ACTION_IDS) {
        const formData = new FormData();
        formData.append('executeActionDTO', JSON.stringify({
            actionId: id, viewMode: false, paramProperties: {},
        }));
        const r = await fetch('/api/v1/actions/execute', {
            method: 'POST', credentials: 'include',
            headers: { 'X-XSRF-TOKEN': xsrf },
            body: formData,
        });
        const j = await r.json();
        const data = j.data || {};
        const entry = {
            id,
            ok: !!j.responseMeta?.success && data.isExecutionSuccess !== false,
            statusCode: data.statusCode,
            isExecutionSuccess: data.isExecutionSuccess,
            body: data.body,
        };
        // Surface the plugin's own messages + error details — a failed EXEC / OUTPUT-param
        // procedure often reports the real reason here, not in `body` (feedback item 12).
        if (Array.isArray(data.messages) && data.messages.length) entry.messages = data.messages;
        if (data.pluginErrorDetails) entry.pluginErrorDetails = data.pluginErrorDetails;
        if (data.dataTypes) entry.dataTypes = data.dataTypes;
        if (evalSynced === false) entry.evalSyncWarning = "eval worker did not confirm appsmith.store sync within 4s; a store-bound binding may have resolved against a stale value";
        if (!entry.ok) {
            entry.error = (data.pluginErrorDetails && (data.pluginErrorDetails.downstreamErrorMessage || data.pluginErrorDetails.appsmithErrorMessage))
                || (Array.isArray(data.messages) && data.messages.join("; "))
                || (data.body && data.body.message)
                || j.responseMeta?.error?.message
                || null;
        }
        out.push(entry);
    }
    return out;
})()
