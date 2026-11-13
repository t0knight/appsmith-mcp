(() => {
    const s = window.__store.getState();

    // `sections` scopes the heavy verbose payload so it does not blow the token limit on a
    // large app. When a non-empty SECTIONS list is injected, only those sections are
    // included (valid: widgets, queries, jsObjects, datasources, connections) and widget
    // property detail follows the "widgets" membership. When SECTIONS is empty/absent the
    // VERBOSE boolean governs everything (all or nothing), preserving the old behaviour.
    const sections = (typeof SECTIONS !== 'undefined' && Array.isArray(SECTIONS) && SECTIONS.length) ? new Set(SECTIONS) : null;
    const wantAll = !sections;
    const want = (name) => wantAll ? VERBOSE : sections.has(name);
    const anyVerbose = VERBOSE || !!sections;

    const pages = (s.entities.pageList?.pages || []).map(p => ({
        id: p.pageId, name: p.pageName, isDefault: !!p.isDefault, isHidden: !!p.isHidden,
        slug: p.slug, isCurrent: p.pageId === s.entities.pageList?.currentPageId,
    }));

    const cw = s.entities.canvasWidgets || {};
    const widgetDetail = want("widgets");
    const buildTree = (id) => {
        const w = cw[id];
        if (!w) return null;
        const node = {
            id: w.widgetId, name: w.widgetName, type: w.type,
            parent: w.parentId,
            position: { left: w.leftColumn, top: w.topRow, right: w.rightColumn, bottom: w.bottomRow },
            children: (w.children || []).map(buildTree).filter(Boolean),
        };
        if (widgetDetail) {
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
    if (!anyVerbose) return result;

    const datasources = want("datasources") ? (s.entities.datasources?.list || []).map(d => ({
        id: d.id, name: d.name, pluginId: d.pluginId, workspaceId: d.workspaceId,
        datasourceStorages: d.datasourceStorages,
    })) : undefined;

    const queries = want("queries") ? (s.entities.actions || []).map(a => ({
        id: a.config?.id, name: a.config?.name, pageId: a.config?.pageId,
        pluginId: a.config?.pluginId, datasourceId: a.config?.datasource?.id,
        actionConfiguration: a.config?.actionConfiguration,
        runBehaviour: a.config?.runBehaviour,
    })) : undefined;

    const jsObjects = want("jsObjects") ? (s.entities.jsActions || []).map(j => ({
        id: j.config?.id, name: j.config?.name, pageId: j.config?.pageId,
        body: j.config?.body,
        actions: (j.config?.actions || []).map(act => ({
            id: act.id, name: act.name,
            body: act.actionConfiguration?.body,
        })),
        variables: j.config?.variables,
    })) : undefined;

    // Connections: for every widget with dynamic bindings, capture the bound paths and
    // their expression strings, then list entity names referenced in the expression.
    const wantConnections = want("connections");
    const entityNames = new Set([
        ...((s.entities.actions || []).map(a => a.config?.name)),
        ...((s.entities.jsActions || []).map(j => j.config?.name)),
        ...((s.entities.datasources?.list || []).map(d => d.name)),
    ].filter(Boolean));
    const connections = [];
    const getAtPath = (obj, path) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj);
    for (const w of (wantConnections ? Object.values(cw) : [])) {
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

    const verbose = { ...result };
    if (datasources !== undefined) verbose.datasources = datasources;
    if (queries !== undefined) verbose.queries = queries;
    if (jsObjects !== undefined) verbose.jsObjects = jsObjects;
    if (wantConnections) verbose.connections = connections;
    return verbose;
})()
