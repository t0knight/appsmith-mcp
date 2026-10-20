(() => {
    const d = window.__store.getState().ui.debugger || {};
    // Query responses are where customer data lives; evaluation/render errors are
    // Appsmith's own text and are the only thing that explains a blank widget.
    const isQueryPayload = e => !!(e && e.source && e.source.type === "ACTION");
    const trim = e => {
        const out = {
            severity: e.severity,
            category: e.category,
            timestamp: e.timestamp,
            logType: e.logType,
            occurrenceCount: e.occurrenceCount,
            sourceName: e.source && e.source.name,
            sourceType: e.source && e.source.type,
            propertyPath: e.source && e.source.propertyPath,
        };
        if (INCLUDE_MESSAGES) {
            const msgs = (e.messages || [])
                .map(m => m && (m.message || m.originalMessage))
                .filter(Boolean);
            if (e.text) out.text = e.text;
            if (msgs.length) out.messages = msgs;
            if (isQueryPayload(e)) {
                // Keep the failure reason, drop the row payload that follows it.
                if (out.messages) out.messages = out.messages.map(m => String(m).slice(0, 300));
                out.payloadTruncated = true;
            }
        }
        return out;
    };
    const filterSev = arr => SEVERITY ? arr.filter(e => e.severity === SEVERITY) : arr;
    const logs = filterSev(d.logs || []).slice(-LIMIT).map(trim);
    const errors = filterSev(Object.values(d.errors || {})).slice(-LIMIT).map(trim);
    return { logs, errors };
})()
