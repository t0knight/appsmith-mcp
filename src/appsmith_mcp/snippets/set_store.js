(() => {
    // Write appsmith.store the real way — dispatch UPDATE_APP_STORE so the value lands in Redux AND
    // the eval tree (bindings re-evaluate immediately), instead of hacking localStorage + reload.
    // `persist:true` also writes the app's persistent localStorage store so the value survives a
    // reload (mirroring storeValue(key, value, true)). This runs on the main thread; JS-object code
    // runs in a worker that can't reach window, which is why storeValue isn't callable from there.
    const store = window.__store;
    const s = store.getState();
    const appId = s.ui.applications?.currentApplication?.id;
    const branch = s.ui.applications?.currentApplication?.gitApplicationMetadata?.branchName;
    const cur = { ...(store.getState().entities.app.store || {}) };
    const persistKey = "APPSMITH_LOCAL_STORE-" + appId + (branch ? "-" + branch : "");
    let ls = {};
    try { ls = JSON.parse(localStorage.getItem(persistKey) || "{}"); } catch (e) {}
    const applied = [];
    for (const e of (ENTRIES || [])) {
        cur[e.key] = e.value;
        if (e.persist) ls[e.key] = e.value;
        applied.push({ key: e.key, persist: !!e.persist });
    }
    store.dispatch({ type: "UPDATE_APP_STORE", payload: cur });
    try { localStorage.setItem(persistKey, JSON.stringify(ls)); } catch (e) {}
    return { applied, store: cur };
})()
