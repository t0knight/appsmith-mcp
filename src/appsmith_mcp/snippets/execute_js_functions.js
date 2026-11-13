(() => {
    const store = window.__store;

    // Snapshot the debugger error keys BEFORE dispatching, so afterwards we can attribute only
    // NEW errors to this run (the debugger.errors map is keyed and persists old entries).
    const errorsBefore = new Set(Object.keys(store.getState().ui.debugger?.errors || {}));
    const errMsg = e => {
        if (!e) return null;
        if (Array.isArray(e.messages) && e.messages.length) {
            return e.messages.map(m => (m && (m.message || m.text)) || String(m)).join("; ");
        }
        return e.text || e.message || null;
    };
    // New debugger errors whose source entity is this collection (a thrown runtime exception
    // during a RUN_BUTTON execution lands here, not in the eval tree).
    const newErrorsFor = collName => {
        const errs = store.getState().ui.debugger?.errors || {};
        return Object.entries(errs)
            .filter(([k, e]) => !errorsBefore.has(k) && e && e.source && e.source.name === collName)
            .map(([, e]) => ({ message: errMsg(e), path: e.source && e.source.propertyPath }))
            .filter(x => x.message);
    };

    const dispatched = [];
    for (const e of EXECUTIONS) {
        const col = (store.getState().entities.jsActions || []).find(j => j.config?.id === e.js_object_id);
        if (!col) { dispatched.push({ error: `js object ${e.js_object_id} not found`, jsObjectId: e.js_object_id }); continue; }
        const action = (col.config.actions || []).find(a => a.name === e.function_name);
        if (!action) { dispatched.push({ error: `function ${e.function_name} not found in ${col.config.name}`, jsObjectId: e.js_object_id, functionName: e.function_name }); continue; }
        store.dispatch({
            type: "START_EXECUTE_JS_FUNCTION",
            payload: { collection: col.config, action, from: "RUN_BUTTON" },
        });
        dispatched.push({ collection: col.config.name, function: e.function_name, jsObjectId: e.js_object_id, actionId: action.id });
    }

    // The return value lands in entities.jsActions[<collection>].data keyed by the
    // function's actionId (NOT in evaluations.tree[collection][`${fn}.data`], which stays
    // empty for a RUN_BUTTON execution).
    const readResult = (jsObjectId, actionId) => {
        const coll = (store.getState().entities.jsActions || []).find(j => j.config?.id === jsObjectId);
        const data = coll && coll.data;
        if (data && Object.prototype.hasOwnProperty.call(data, actionId)) return { has: true, value: data[actionId] };
        return { has: false };
    };

    // Poll until each function's result appears OR a new error is attributed to it (fail fast on
    // a thrown exception instead of waiting out the whole timeout), or until timeout.
    const start = Date.now();
    const TIMEOUT = 6000;
    return new Promise(resolve => {
        const tick = () => {
            const rows = dispatched.map(d => {
                if (d.error) return { done: true, out: d };
                const r = readResult(d.jsObjectId, d.actionId);
                const errs = newErrorsFor(d.collection);
                return {
                    done: r.has || errs.length > 0,
                    out: { dispatched: true, collection: d.collection, function: d.function, result: r.has ? r.value : undefined, _has: r.has, _errs: errs },
                };
            });
            const pending = rows.some(r => !r.done);
            if (!pending || Date.now() - start > TIMEOUT) {
                const out = rows.map(r => {
                    const o = r.out;
                    if (o.dispatched) {
                        if (o._errs && o._errs.length) {
                            o.ok = false;
                            o.error = o._errs.map(e => e.message).join(" | ");
                            o.errors = o._errs;
                        } else if (o._has) {
                            o.ok = true;
                        } else {
                            o.ok = false;
                            o.note = "result not captured within timeout — the function may still be running or returned nothing (no error was reported)";
                        }
                    }
                    delete o._has; delete o._errs;
                    return o;
                });
                resolve(out);
            } else {
                setTimeout(tick, 150);
            }
        };
        setTimeout(tick, 150);
    });
})()
