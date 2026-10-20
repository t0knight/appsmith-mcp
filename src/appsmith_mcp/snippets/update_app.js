(async () => {
    const store = window.__store;
    const s = store.getState();
    const cur = s.ui.applications?.currentApplication;
    const appId = APP_ID || cur?.id;
    if (!appId) return { error: "no app id and no current application" };
    const oldSlug = cur?.slug || null;
    const workspaceId = cur?.workspaceId;
    const data = {};
    if (NAME) data.name = NAME;
    if (ICON) data.icon = ICON;
    if (COLOR) data.color = COLOR;

    const detail = {};
    if (NAVIGATION && Object.keys(NAVIGATION).length) detail.navigationSetting = NAVIGATION;
    if (THEME_SETTINGS && Object.keys(THEME_SETTINGS).length) detail.themeSetting = THEME_SETTINGS;
    if (POSITIONING && Object.keys(POSITIONING).length) detail.appPositioning = POSITIONING;
    if (Object.keys(detail).length) data.applicationDetail = detail;

    if (Object.keys(data).length === 0) {
        return { error: "nothing to update — pass name/icon/color/navigation/theme_settings/positioning" };
    }
    store.dispatch({
        type: "UPDATE_APPLICATION",
        payload: { id: appId, ...data },
    });

    // A rename regenerates the URL slug server-side, silently breaking every existing
    // /app/<slug>/... URL (email links, the Supabase Site/Redirect URLs, bookmarks). The store's
    // currentApplication.slug does NOT refresh after the optimistic rename, so read the AUTHORITATIVE
    // slug from the apps API (same source as list_apps), polling until the rename PUT lands.
    let newSlug = oldSlug;
    if (NAME && workspaceId) {
        for (let i = 0; i < 20; i++) {
            await new Promise(r => setTimeout(r, 150));
            try {
                const r = await fetch(`/api/v1/applications/home?workspaceId=${workspaceId}`, { credentials: "include", headers: { "Accept": "application/json" } });
                const j = await r.json();
                const a = (j.data || []).find(x => x.id === appId);
                if (a && a.slug) { newSlug = a.slug; if (a.slug !== oldSlug) break; }
            } catch (e) {}
        }
    }

    const slugChanged = !!(NAME && newSlug && newSlug !== oldSlug);
    const res = { dispatched: true, id: appId, applied: data, oldSlug, newSlug, slugChanged };
    if (slugChanged) {
        res.warning = `App slug changed "${oldSlug}" -> "${newSlug}". Every /app/${oldSlug}/... URL now breaks — update email-template links, the Supabase Site/Redirect URLs, and any bookmarks to /app/${newSlug}/...`;
    } else if (NAME) {
        res.warning = "Renaming an app regenerates its URL slug; confirm newSlug above and update any /app/<slug>/... URLs if it changed.";
    }
    return res;
})()
