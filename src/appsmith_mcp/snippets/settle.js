(async () => {
    const store = window.__store;
    const pending = () =>
        (store.getState().entities.actions || [])
            .filter(a => a && a.isLoading)
            .map(a => a.config && a.config.name)
            .filter(Boolean);
    const skeletons = () =>
        document.querySelectorAll(".bp3-skeleton, .t--widget-skeleton, [class*='skeleton']").length;
    const artboard = () =>
        !!document.querySelector(".t--canvas-artboard, [data-testid='t--canvas-artboard']");
    // A page just reloaded shows a grey skeleton for a beat; measuring or screenshotting then
    // reads the loading state as the result. Wait until the artboard is up, no query is in
    // flight and no skeleton cell remains — bounded, so a stuck load still returns.
    let settled = false;
    for (let i = 0; i < 24; i++) {
        if (artboard() && pending().length === 0 && skeletons() === 0) { settled = true; break; }
        await new Promise(r => setTimeout(r, 250));
    }
    return { settled, pendingQueries: pending() };
})()
