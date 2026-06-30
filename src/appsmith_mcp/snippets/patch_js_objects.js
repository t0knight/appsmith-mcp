(() => {
    const out = [];
    for (const e of EDITS) {
        const r = { target_id: e.target_id };
        if (!e.old) { out.push({ ...r, error: "`old` is empty" }); continue; }

        const col = (window.__store.getState().entities.jsActions || []).find(j => j.config?.id === e.target_id);
        if (!col) { out.push({ ...r, error: "js object not found" }); continue; }

        const source = col.config?.body;
        if (typeof source !== "string") {
            out.push({ ...r, error: "target code is not a string" });
            continue;
        }

        const count = source.split(e.old).length - 1;
        if (count === 0) {
            out.push({ ...r, error: "`old` not found in target code" });
            continue;
        }
        if (count > 1 && !e.replace_all) {
            out.push({ ...r, error: `\`old\` matches ${count} times; pass replace_all to replace every occurrence` });
            continue;
        }
        const replacements = e.replace_all ? count : 1;
        const updated = e.replace_all
            ? source.split(e.old).join(e.new)
            : source.slice(0, source.indexOf(e.old)) + e.new + source.slice(source.indexOf(e.old) + e.old.length);

        window.__store.dispatch({
            type: "UPDATE_JS_ACTION_BODY_INIT",
            payload: { id: e.target_id, body: updated, isReplay: false },
        });
        out.push({ ...r, name: col.config?.name, replacements });
    }
    return out;
})()
