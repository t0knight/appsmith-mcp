(() => {
    const s = window.__store.getState();
    const selectedPageId = s.entities.pageList?.currentPageId || null;
    const renderedPageId = s.ui.editor?.currentPageId || null;
    const pages = s.entities.pageList?.pages || [];
    const nameOf = (id) => { const p = pages.find(x => x.pageId === id); return p ? (p.pageName || p.name) : null; };
    const url = (typeof location !== "undefined") ? location.href : null;
    // The editor URL carries the page id as `...page<slug>-<id>/edit`; pull the 24-hex id.
    const m = url && url.match(/[0-9a-f]{24}/i);
    const urlPageId = m ? m[0] : null;
    // Mutations target the SELECTED page's layout but write the RENDERED page's widgets; when
    // these differ the canvas hasn't actually loaded the selected page (see switch_page).
    const consistent = !!renderedPageId && renderedPageId === selectedPageId;
    const moduleId = s.ui.editor?.currentModuleId;
    const module = moduleId && (s.entities.modules || {})[moduleId];
    if (module) {
        // Package module editor: mutations land on this module's layout/entities.
        return {
            context: "module",
            moduleId,
            moduleName: module.name,
            moduleType: module.type,
            packageId: module.packageId || s.ui.editor?.currentPackageId,
            url,
            consistent: true,
            // The package editor sets the module up and fetches its queries/JS after the store exists.
            ready: s.ui.editor?.isPackageEditorInitialized !== false && !s.ui.editor?.isSettingUpModule && !s.ui.editor?.isModuleFetchingEntities,
            rootChildren: (s.entities.canvasWidgets?.["0"]?.children || []).length,
        };
    }
    return {
        context: "page",
        selectedPageId,
        renderedPageId,
        selectedPageName: nameOf(selectedPageId),
        renderedPageName: nameOf(renderedPageId),
        url,
        urlPageId,
        consistent,
        rootChildren: (s.entities.canvasWidgets?.["0"]?.children || []).length,
        applicationId: s.ui.applications?.currentApplication?.id || null,
    };
})()
