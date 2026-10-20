(() => {
    const cwAll = window.__store.getState().entities.canvasWidgets || {};
    const results = [];
    const work = {}; // widget_id -> working srcDoc copy

    const escapeRegex = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const tokens = source => {
        const out = [];
        let i = 0;
        while (i < source.length) {
            const c = source[i];
            const next = source[i + 1] || "";
            if (/\s/.test(c)) { i += 1; continue; }
            if (c === "/" && next === "/") {
                let end = source.indexOf("\n", i + 2);
                if (end < 0) end = source.length;
                out.push(source.slice(i, end));
                i = end;
                continue;
            }
            if (c === "/" && next === "*") {
                let end = source.indexOf("*/", i + 2);
                end = end < 0 ? source.length : end + 2;
                out.push(source.slice(i, end));
                i = end;
                continue;
            }
            if (c === "'" || c === '"' || c === "`") {
                const quote = c;
                let end = i + 1;
                while (end < source.length) {
                    if (source[end] === "\\") { end += 2; continue; }
                    if (source[end] === quote) { end += 1; break; }
                    end += 1;
                }
                out.push(source.slice(i, end));
                i = end;
                continue;
            }
            if (/[A-Za-z0-9_$#-]/.test(c)) {
                let end = i + 1;
                while (end < source.length && /[A-Za-z0-9_$#-]/.test(source[end])) end += 1;
                out.push(source.slice(i, end));
                i = end;
                continue;
            }
            out.push(c);
            i += 1;
        }
        return out;
    };
    const normalizedMatches = (source, needle) => {
        const parts = tokens(needle);
        if (!parts.length) return [];
        const pattern = parts.map(escapeRegex).join("\\s*");
        let regex;
        try { regex = new RegExp(pattern, "g"); } catch (_) { return []; }
        const matches = [];
        let match;
        while ((match = regex.exec(source)) !== null) {
            matches.push({ index: match.index, length: match[0].length });
            if (!match[0].length) regex.lastIndex += 1;
        }
        return matches;
    };

    for (const e of EDITS) {
        const r = { widget_id: e.widget_id };
        if (!e.old) { results.push({ ...r, error: "`old` is empty" }); continue; }
        if (!["html", "css", "js"].includes(e.field)) {
            results.push({ ...r, error: "`field` must be one of html|css|js" });
            continue;
        }
        const w = cwAll[e.widget_id];
        if (!w) { results.push({ ...r, error: "widget not found on the current page. Fan-out reaches only the loaded page — if this widget is on another page, switch_page to it and retry; for a custom widget replicated across pages, use sync_custom_widget from a source on this page." }); continue; }
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

        const literalCount = cur.split(e.old).length - 1;
        const matches = literalCount === 0 ? normalizedMatches(cur, e.old) : [];
        const count = literalCount || matches.length;
        const matchMode = literalCount ? "literal" : "normalized";
        if (count === 0) {
            results.push({ ...r, error: "`old` not found in target code" });
            continue;
        }
        if (count > 1 && !e.replace_all) {
            results.push({ ...r, error: `\`old\` matches ${count} times; pass replace_all to replace every occurrence` });
            continue;
        }
        const replacements = e.replace_all ? count : 1;
        if (literalCount) {
            work[e.widget_id][e.field] = e.replace_all
                ? cur.split(e.old).join(e.new)
                : cur.slice(0, cur.indexOf(e.old)) + e.new + cur.slice(cur.indexOf(e.old) + e.old.length);
        } else {
            const selected = e.replace_all ? matches : matches.slice(0, 1);
            let updated = cur;
            for (const match of [...selected].reverse()) {
                updated = updated.slice(0, match.index) + e.new + updated.slice(match.index + match.length);
            }
            work[e.widget_id][e.field] = updated;
        }
        results.push({ ...r, name: w.widgetName, field: e.field, replacements, matchMode });
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
