(async (result) => {
    const store = window.__store;
    const ls = () => store.getState().ui.editor?.loadingStates || {};
    await new Promise((resolve) => {
        let sawSaving = false, done = false;
        const finish = () => {
            if (done) return;
            done = true;
            unsub();
            clearTimeout(idleTimer);
            clearTimeout(hardTimer);
            resolve();
        };
        const check = () => {
            const s = ls();
            if (s.saving || s.savingEntity) sawSaving = true;
            else if (sawSaving) finish();
        };
        const unsub = store.subscribe(check);
        // SAVE_PAGE_INIT is debounced 500ms; if no save starts in that window
        // there is nothing to wait for.
        const idleTimer = setTimeout(() => { if (!sawSaving) finish(); }, 900);
        const hardTimer = setTimeout(finish, 8000);
        check();
    });
    return result;
})
