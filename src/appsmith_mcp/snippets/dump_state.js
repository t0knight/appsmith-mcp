(() => {
    const s = window.__store.getState();

    const pages = (s.entities.pageList?.pages || []).map(p => ({
        id: p.pageId, name: p.pageName, isDefault: !!p.isDefault, isHidden: !!p.isHidden,
        slug: p.slug, isCurrent: p.pageId === s.entities.pageList?.currentPageId,
    }));

    const cw = s.entities.canvasWidgets || {};
    const buildTree = (id) => {
        const w = cw[id];
        if (!w) return null;
        const node = {
            id: w.widgetId, name: w.widgetName, type: w.type,
            parent: w.parentId,
            position: { left: w.leftColumn, top: w.topRow, right: w.rightColumn, bottom: w.bottomRow },
            children: (w.children || []).map(buildTree).filter(Boolean),
        };
        if (VERBOSE) {
            const props = {};
            for (const [k, v] of Object.entries(w)) {
                if (k === "children") continue;
                props[k] = v;
            }
            node.properties = props;
        }
        return node;
    };
    const widgets = buildTree("0");

    const result = {
        url: window.location.href,
        application: {
            id: s.ui.applications?.currentApplication?.id,
            name: s.ui.applications?.currentApplication?.name,
            slug: s.ui.applications?.currentApplication?.slug,
        },
        pages,
        widgets,
    };
    if (!VERBOSE) return result;

    const datasources = (s.entities.datasources?.list || []).map(d => ({
        id: d.id, name: d.name, pluginId: d.pluginId, workspaceId: d.workspaceId,
        datasourceStorages: d.datasourceStorages,
    }));

    const queries = (s.entities.actions || []).map(a => ({
        id: a.config?.id, name: a.config?.name, pageId: a.config?.pageId,
        pluginId: a.config?.pluginId, datasourceId: a.config?.datasource?.id,
        actionConfiguration: a.config?.actionConfiguration,
        runBehaviour: a.config?.runBehaviour,
    }));

    const jsObjects = (s.entities.jsActions || []).map(j => ({
        id: j.config?.id, name: j.config?.name, pageId: j.config?.pageId,
        body: j.config?.body,
        actions: (j.config?.actions || []).map(act => ({
            id: act.id, name: act.name,
            body: act.actionConfiguration?.body,
        })),
        variables: j.config?.variables,
    }));

    // Connections: for every widget with dynamic bindings, capture the bound paths and
    // their expression strings, then list entity names referenced in the expression.
    const entityNames = new Set([
        ...queries.map(q => q.name),
        ...jsObjects.map(o => o.name),
        ...datasources.map(d => d.name),
    ].filter(Boolean));
    const connections = [];
    const getAtPath = (obj, path) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj);
    for (const w of Object.values(cw)) {
        const paths = w.dynamicBindingPathList || [];
        for (const p of paths) {
            const expr = getAtPath(w, p.key);
            if (typeof expr !== 'string') continue;
            const referenced = [...entityNames].filter(n => expr.includes(n));
            connections.push({
                sourceWidget: w.widgetName,
                sourceWidgetId: w.widgetId,
                propertyPath: p.key,
                expression: expr,
                referencedEntities: referenced,
            });
        }
        // Trigger paths (onClick, onChange, etc.)
        const triggers = w.dynamicTriggerPathList || [];
        for (const t of triggers) {
            const expr = getAtPath(w, t.key);
            if (typeof expr !== 'string') continue;
            const referenced = [...entityNames].filter(n => expr.includes(n));
            connections.push({
                sourceWidget: w.widgetName,
                sourceWidgetId: w.widgetId,
                propertyPath: t.key,
                expression: expr,
                isTrigger: true,
                referencedEntities: referenced,
            });
        }
    }

    return { ...result, datasources, queries, jsObjects, connections };
})()
