(() => {
    const dispatched = [];
    for (const e of EXECUTIONS) {
        const col = (window.__store.getState().entities.jsActions || []).find(j => j.config?.id === e.js_object_id);
        if (!col) { dispatched.push({ error: `js object ${e.js_object_id} not found`, jsObjectId: e.js_object_id }); continue; }
        const action = (col.config.actions || []).find(a => a.name === e.function_name);
        if (!action) { dispatched.push({ error: `function ${e.function_name} not found in ${col.config.name}`, jsObjectId: e.js_object_id, functionName: e.function_name }); continue; }
        window.__store.dispatch({
            type: "START_EXECUTE_JS_FUNCTION",
            payload: { collection: col.config, action, from: "RUN_BUTTON" },
        });
        dispatched.push({ collection: col.config.name, function: e.function_name, jsObjectId: e.js_object_id });
    }
    return new Promise(res => setTimeout(() => {
        const ev = window.__store.getState().evaluations?.tree || {};
        const out = dispatched.map(d => {
            if (d.error) return d;
            const result = ev[d.collection]?.[`${d.function}.data`];
            return {
                dispatched: true,
                collection: d.collection,
                function: d.function,
                result,
                note: result === undefined || (result && typeof result === 'object' && Object.keys(result).length === 0)
                    ? "result not captured (eval tree empty); function may still have run"
                    : undefined,
            };
        });
        res(out);
    }, 2000));
})()
