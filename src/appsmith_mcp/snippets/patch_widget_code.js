(() => {
    const cwAll = window.__store.getState().entities.canvasWidgets || {};
    const results = [];
    const work = {}; // widget_id -> working srcDoc copy

    for (const e of EDITS) {
        const r = { widget_id: e.widget_id };
        if (!e.old) { results.push({ ...r, error: "`old` is empty" }); continue; }
        if (!["html", "css", "js"].includes(e.field)) {
            results.push({ ...r, error: "`field` must be one of html|css|js" });
            continue;
        }
        const w = cwAll[e.widget_id];
        if (!w) { results.push({ ...r, error: "widget not found" }); continue; }
        if (w.type !== "CUSTOM_WIDGET") {
            results.push({ ...r, error: `target is ${w.type}, expected a CUSTOM_WIDGET` });
            continue;
        }

        if (!work[e.widget_id]) work[e.widget_id] = { ...(w.srcDoc || {}) };
        const cur = work[e.widget_id][e.field];
        if (typeof cur !== "string") {
            results.push({ ...r, error: "target code is not a string" });
            continue;
        }

        const count = cur.split(e.old).length - 1;
        if (count === 0) {
            results.push({ ...r, error: "`old` not found in target code" });
            continue;
        }
        if (count > 1 && !e.replace_all) {
            results.push({ ...r, error: `\`old\` matches ${count} times; pass replace_all to replace every occurrence` });
            continue;
        }
        const replacements = e.replace_all ? count : 1;
        work[e.widget_id][e.field] = e.replace_all
            ? cur.split(e.old).join(e.new)
            : cur.slice(0, cur.indexOf(e.old)) + e.new + cur.slice(cur.indexOf(e.old) + e.old.length);
        results.push({ ...r, name: w.widgetName, field: e.field, replacements });
    }

    // Collect changed fields for the caller to format and write back.
    const fields = [];
    for (const [wid, sd] of Object.entries(work)) {
        const orig = cwAll[wid].srcDoc || {};
        for (const f of ["html", "css", "js"]) {
            if (sd[f] !== undefined && sd[f] !== orig[f]) fields.push({ widget_id: wid, field: f, value: sd[f] });
        }
    }
    return { results, fields };
})()
