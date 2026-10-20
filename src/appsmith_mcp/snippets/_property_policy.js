// Shared widget-property policy. Raw JS *expression* (a function) injected into add_widgets /
// update_widgets via run_snippet(js_helpers={...}). It turns caller props into exactly what the
// Appsmith property pane would store:
//
//   - {{ }} leaves → dynamicBindingPathList; on* / declared event keys → dynamicTriggerPathList.
//   - dynamicPropertyPathList (the pane's "JS" toggle): a JS-convertible property whose value is a
//     binding is only shown as code when its path is listed there — otherwise the pane renders the
//     visual control (switch/dropdown/colour/data selector), which can't show the binding, and the
//     field looks empty to whoever maintains the page. Literals turn the toggle off again.
//   - One-click data selectors (table tableData, select sourceData, ...) only show the chosen query
//     when the value is exactly `{{name.data}}`, so `{{ name.data }}` is normalized to that and kept
//     out of JS mode; anything richer is shown as code.
//   - Supplying select data drops the widget's sample default selection (GREEN...).
//
// Object props deep-merge into the widget's current value unless listed in `replaceKeys`.
// Returns { modify, registered } where `modify` carries the final values + the three path lists.
(({ widget, props, triggerKeys = [], replaceKeys = [] }) => {
    const UI_CONTROLS = /*__UI_CONTROLS__*/{};          // type -> { prop: controlType } (JS-convertible)
    const SAMPLE_DEFAULTS = /*__SAMPLE_DEFAULTS__*/{};  // type -> sample defaultOptionValue
    const ONE_CLICK = "ONE_CLICK_BINDING_CONTROL";

    const bindRe = /\{\{[\s\S]*?\}\}/;
    const isBinding = v => typeof v === "string" && bindRe.test(v);
    const isPlainObject = x => x && typeof x === "object" && !Array.isArray(x);
    const deepMerge = (target, source) => {
        if (!isPlainObject(target) || !isPlainObject(source)) return source;
        const out = { ...target };
        for (const [k, v] of Object.entries(source)) {
            out[k] = isPlainObject(v) && isPlainObject(out[k]) ? deepMerge(out[k], v) : v;
        }
        return out;
    };
    const collectBindings = (val, prefix, out) => {
        if (typeof val === "string") { if (bindRe.test(val)) out.push(prefix); return; }
        if (Array.isArray(val)) { val.forEach((v, i) => collectBindings(v, `${prefix}[${i}]`, out)); return; }
        if (isPlainObject(val)) { for (const [k, v] of Object.entries(val)) collectBindings(v, prefix ? `${prefix}.${k}` : k, out); }
    };
    const dedupe = arr => { const seen = new Set(); return arr.filter(p => (seen.has(p.key) ? false : seen.add(p.key))); };
    const isTriggerPath = p => /^on[A-Z]/.test(p.split(".").pop().split("[")[0]);
    const topOf = key => key.split(".")[0].split("[")[0];
    const simpleQueryData = /^\{\{\s*([A-Za-z_$][\w$]*)\.data\s*\}\}$/;
    const themeBinding = /^\{\{\s*appsmith\.theme\.[^{}]*\}\}$/;
    const sameJson = (a, b) => JSON.stringify(a) === JSON.stringify(b);

    const controls = UI_CONTROLS[widget.type] || {};
    const values = { ...props };

    // One-click data selectors: canonical `{{name.data}}` so the pane's dropdown can show it.
    for (const [k, v] of Object.entries(values)) {
        const m = controls[k] === ONE_CLICK && typeof v === "string" && v.match(simpleQueryData);
        if (m) values[k] = `{{${m[1]}.data}}`;
    }

    // Caller supplied select data but no default → clear the sample selection it was born with.
    const cleared = [];
    if ("sourceData" in values && !("defaultOptionValue" in values) && widget.type in SAMPLE_DEFAULTS
        && sameJson(widget.defaultOptionValue, SAMPLE_DEFAULTS[widget.type])) {
        values.defaultOptionValue = Array.isArray(SAMPLE_DEFAULTS[widget.type]) ? [] : "";
        cleared.push("defaultOptionValue");
    }

    const merged = {};
    for (const [k, v] of Object.entries(values)) {
        merged[k] = !replaceKeys.includes(k) && isPlainObject(v) && isPlainObject(widget[k]) ? deepMerge(widget[k], v) : v;
    }

    const touched = new Set(Object.keys(values));
    const keep = p => !touched.has(topOf(p.key));
    const bindList = (widget.dynamicBindingPathList || []).filter(keep);
    const triggerList = (widget.dynamicTriggerPathList || []).filter(keep);
    const propList = (widget.dynamicPropertyPathList || []).filter(keep);
    const priorJs = new Set((widget.dynamicPropertyPathList || []).map(p => p.key));

    const isTrigger = k => /^on/.test(k) || triggerKeys.includes(k);
    const registered = { bindings: [], triggers: [], literals: [], jsMode: [], clearedSampleDefaults: cleared };
    for (const [k, v] of Object.entries(values)) {
        if (isTrigger(k)) {
            triggerList.push({ key: k });
            registered.triggers.push(k);
            // Custom-widget events have no action-selector UI: the editor keeps them in JS mode.
            if (widget.type === "CUSTOM_WIDGET" || priorJs.has(k)) { propList.push({ key: k }); registered.jsMode.push(k); }
            continue;
        }
        if (isBinding(merged[k])) {
            bindList.push({ key: k });
            registered.bindings.push(k);
        } else if (isPlainObject(merged[k]) || Array.isArray(merged[k])) {
            const nested = [];
            collectBindings(merged[k], k, nested);
            for (const p of nested) {
                if (isTriggerPath(p)) { triggerList.push({ key: p }); registered.triggers.push(p); }
                else { bindList.push({ key: p }); registered.bindings.push(p); }
            }
            if (!nested.length) registered.literals.push(k);
        } else {
            registered.literals.push(k);
        }

        const control = controls[k];
        if (!control) continue;
        const v2 = merged[k];
        let js;
        if (control === ONE_CLICK) js = !(typeof v2 === "string" && simpleQueryData.test(v2)) && v2 !== "" && v2 != null;
        else if (isBinding(v2)) js = !themeBinding.test(v2);
        else js = false;
        if (js) { propList.push({ key: k }); registered.jsMode.push(k); }
    }

    return {
        modify: {
            ...merged,
            dynamicBindingPathList: dedupe(bindList),
            dynamicTriggerPathList: dedupe(triggerList),
            dynamicPropertyPathList: dedupe(propList),
        },
        registered,
    };
})
