(() => {
    // Read the EVALUATED value of any binding/property off the eval dataTree — the actual runtime
    // value Appsmith computed (e.g. tb.primaryColumns.id_local.selectOptions, q_x.data,
    // jsObj.myVar), which the write tools' "applied" summary can't tell you. Paths are
    // "<entityName>.<dotted.path>" and may include array indices (data[0].name).
    const tree = window.__store.getState().evaluations?.tree || {};
    const get = (obj, path) => path.split(".").reduce((o, seg) => {
        if (o == null) return o;
        const m = seg.match(/^([^\[]+)((?:\[\d+\])*)$/);
        if (!m) return o[seg];
        let v = o[m[1]];
        for (const idx of (m[2].match(/\d+/g) || [])) v = v == null ? v : v[+idx];
        return v;
    }, obj);
    const out = {};
    for (const p of (PATHS || [])) {
        try { out[p] = get(tree, p); } catch (e) { out[p] = null; }
    }
    return out;
})()
