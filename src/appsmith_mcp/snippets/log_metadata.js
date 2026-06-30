(() => {
    const d = window.__store.getState().ui.debugger || {};
    const trim = e => ({
        severity: e.severity,
        category: e.category,
        timestamp: e.timestamp,
        logType: e.logType,
        occurrenceCount: e.occurrenceCount,
        sourceName: e.source && e.source.name,
        sourceType: e.source && e.source.type,
    });
    const filterSev = arr => SEVERITY ? arr.filter(e => e.severity === SEVERITY) : arr;
    const logs = filterSev(d.logs || []).slice(-LIMIT).map(trim);
    const errors = filterSev(Object.values(d.errors || {})).slice(-LIMIT).map(trim);
    return { logs, errors };
})()
