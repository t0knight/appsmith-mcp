(async () => {
    // Package module instances on the CURRENT page, as the page editor manages them.
    // OP: list | add | update | delete | pull.
    const store = window.__store;
    const state = store.getState();
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    const api = async (method, url, body) => {
        const r = await fetch(url, {
            method, credentials: "include",
            headers: { "Content-Type": "application/json", "Accept": "application/json", "X-XSRF-TOKEN": xsrf },
            body: body === undefined ? undefined : JSON.stringify(body),
        });
        let j = null;
        try { j = await r.json(); } catch (e) {}
        const ok = r.status < 300 && j && j.responseMeta && j.responseMeta.success !== false;
        return { ok, status: r.status, data: j && j.data, error: (j && j.responseMeta && j.responseMeta.error && j.responseMeta.error.message) || (ok ? null : `HTTP ${r.status}`) };
    };
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const appId = state.ui.applications?.currentApplication?.id;
    const pageId = state.entities.pageList?.currentPageId;
    if (state.ui.editor?.currentModuleId || !appId || !pageId) {
        return { error: "open an application page in the editor first (module instances live on app pages)",
            context: { moduleId: state.ui.editor?.currentModuleId || null, applicationId: appId || null, pageId: pageId || null } };
    }
    const listInstances = async () => {
        const r = await api("GET", `/api/v1/moduleInstances?contextId=${pageId}&contextType=PAGE&viewMode=false`);
        return r.ok ? (r.data || []) : [];
    };
    const consumables = async () => {
        const r = await api("GET", `/api/v1/packages/consumables?branchedApplicationId=${appId}`);
        return r.ok ? r.data : { packages: [], modules: [] };
    };
    const pullStatus = async () => {
        const r = await api("GET", `/api/v1/packages/${appId}/poll-pull-status`);
        return r.ok ? r.data : null;
    };
    const refresh = () => store.dispatch({ type: "SETUP_MODULE_INSTANCE_INIT", payload: { contextId: pageId, contextType: "PAGE", viewMode: false } });
    const findInstance = (list, ref) => list.find(i => i.id === ref || i.name === ref);
    const putInstance = async (inst, inputs) => {
        const body = { ...inst, inputs: { ...(inst.inputs || {}), ...inputs } };
        delete body.layouts;
        return api("PUT", `/api/v1/moduleInstances/${inst.id}`, body);
    };

    if (OP === "list") {
        const [list, cons, status] = [await listInstances(), await consumables(), await pullStatus()];
        const modName = id => (cons.modules || []).find(m => m.id === id)?.name;
        return {
            instances: list.map(i => ({
                id: i.id, name: i.name, type: i.type, module: modName(i.sourceModuleId) || null, moduleUUID: i.moduleUUID,
                inputs: i.inputs || {}, outputs: Object.keys(i.outputs || {}),
            })),
            available: (cons.modules || []).map(m => ({ name: m.name, type: m.type, moduleUUID: m.moduleUUID, id: m.id,
                originModuleId: m.originModuleId || null,
                versions: Object.fromEntries(Object.entries(m).filter(([k]) => /version/i.test(k))),
                package: (cons.packages || []).find(p => p.id === m.packageId)?.name || null })),
            packageUpdates: status,
        };
    }

    if (OP === "add") {
        const cons = await consumables();
        const cw = state.entities.canvasWidgets || {};
        const out = [];
        // The same module can appear in more than one version; use the one other pages of this app already use
        // (the server refuses an older version: "You are working with an older version of this module").
        let usadas = null;
        const versaoDoApp = async (uuid) => {
            if (!usadas) {
                usadas = [];
                for (const pg of (state.entities.pageList?.pages || [])) {
                    const r = await api("GET", `/api/v1/moduleInstances?contextId=${pg.pageId}&contextType=PAGE&viewMode=false`);
                    if (r.ok) usadas.push(...(r.data || []));
                }
            }
            return usadas.find(i => i.moduleUUID === uuid)?.sourceModuleId || null;
        };
        for (const spec of ARGS.instances) {
            const candidatos = (cons.modules || []).filter(m => [m.name, m.id, m.moduleUUID, m.originModuleId].includes(spec.module));
            const base = candidatos[candidatos.length - 1];
            const preferida = base ? await versaoDoApp(base.moduleUUID) : null;
            // A JS/query instance is created by API: use the version id other pages already use, even when the
            // consumables list still shows the older one.
            const mod = candidatos.find(m => m.id === preferida) || (base && preferida && base.type !== "UI_MODULE"
                ? { ...base, id: preferida } : base);
            if (!mod) { out.push({ name: spec.name, error: `module ${spec.module} is not available to this app (published packages of the workspace only)` }); continue; }
            let inst = null;
            if (mod.type === "UI_MODULE") {
                // Same as dragging the module onto the canvas: the editor creates the instance and saves the page.
                let parentId = spec.parent_id || "0";
                if (cw[parentId] && cw[parentId].type !== "CANVAS_WIDGET") {
                    const inner = Object.values(cw).find(c => c.parentId === parentId && c.type === "CANVAS_WIDGET");
                    if (inner) parentId = inner.widgetId;
                }
                if (!cw[parentId]) { out.push({ name: spec.name, error: `parent ${spec.parent_id} not found` }); continue; }
                const widgetId = "w_" + Math.random().toString(36).slice(2, 10);
                store.dispatch({
                    type: "WIDGET_ADD_CHILD",
                    payload: {
                        widgetId: parentId, type: `MODULE_WIDGET_${mod.moduleUUID}`, newWidgetId: widgetId,
                        leftColumn: spec.left ?? 0, topRow: spec.top ?? 0, columns: spec.columns ?? 64, rows: spec.rows ?? 20,
                        parentRowSpace: 10, parentColumnSpace: 10, props: {}, widgetName: spec.name,
                    },
                });
                const start = Date.now();
                while (Date.now() - start < 15000) {
                    inst = findInstance(await listInstances(), spec.name);
                    if (inst) break;
                    await sleep(500);
                }
                if (!inst) { out.push({ name: spec.name, widgetId, error: "module widget added but the instance did not appear — check get_logs" }); continue; }
                const p = await __persistLayout({});
                if (!p.persisted) { out.push({ name: spec.name, id: inst.id, widgetId, error: p.error }); continue; }
                inst.widgetId = widgetId;
            } else {
                const r = await api("POST", "/api/v1/moduleInstances", { sourceModuleId: mod.id, contextId: pageId, contextType: "PAGE", name: spec.name });
                if (!r.ok) { out.push({ name: spec.name, error: r.error }); continue; }
                inst = r.data.moduleInstance;
            }
            const res = { id: inst.id, name: inst.name, type: mod.type, module: mod.name, ...(inst.widgetId ? { widgetId: inst.widgetId } : {}) };
            if (spec.inputs && Object.keys(spec.inputs).length) {
                const u = await putInstance(inst, spec.inputs);
                if (!u.ok) res.error = `created, but inputs failed: ${u.error}`;
                else res.inputs = { ...(inst.inputs || {}), ...spec.inputs };
            }
            out.push(res);
        }
        refresh();
        return out;
    }

    if (OP === "queries") {
        // Read-only: the query behind each query-module instance (read from the package module it
        // comes from — the instance itself only exposes a stub), so the server can apply the
        // read-only execution policy before running anything.
        const plugins = state.entities.plugins?.list || [];
        const out = [];
        for (const ref of ARGS.instances) {
            const inst = Object.values(state.entities.moduleInstances || {}).find(i => i && (i.id === ref || i.name === ref));
            if (!inst) { out.push({ ref, found: false }); continue; }
            const row = { ref, found: true, id: inst.id, name: inst.name, type: inst.type, action: null };
            if (inst.type === "QUERY_MODULE") {
                try {
                    const pub = (await api("GET", `/api/v1/modules/${inst.sourceModuleId}`)).data || {};
                    const ents = (await api("GET", `/api/v1/modules/${pub.originModuleId || inst.sourceModuleId}/entities`)).data || {};
                    const src = (ents.actions || []).find(a => a.isPublic) || (ents.actions || [])[0];
                    if (src) {
                        row.action = {
                            id: src.id, name: src.name, pluginId: src.pluginId, pluginType: src.pluginType,
                            pluginPackageName: plugins.find(p => p.id === src.pluginId)?.packageName,
                            actionConfiguration: src.actionConfiguration,
                        };
                    }
                } catch (e) { row.action = null; }
            }
            out.push(row);
        }
        return out;
    }

    if (OP === "run") {
        // Same as the query-module instance's Run button: the editor evaluates its inputs.
        const out = [];
        for (const ref of ARGS.instances) {
            const inst = Object.values(state.entities.moduleInstances || {}).find(i => i && (i.id === ref || i.name === ref));
            if (!inst) { out.push({ instance: ref, error: "instance not found on this page" }); continue; }
            if (inst.type !== "QUERY_MODULE") { out.push({ name: inst.name, error: `${inst.type} instances are not queries — call their functions from an event (e.g. {{${inst.name}.fn()}})` }); continue; }
            const pub = () => ((store.getState().entities.moduleInstanceEntities || {}).actions || [])
                .find(a => a.config && a.config.moduleInstanceId === inst.id && a.config.isPublic);
            const before = pub() && pub().data;
            store.dispatch({ type: "RUN_QUERY_MODULE_INSTANCE_INIT", payload: { id: inst.id } });
            const start = Date.now();
            let p = null;
            while (Date.now() - start < 30000) {
                p = pub();
                if (p && p.data && p.data !== before && !p.isLoading) break;
                await sleep(200);
            }
            if (!p || !p.data || p.data === before) { out.push({ name: inst.name, error: "no result within 30s — check get_logs" }); continue; }
            const d = p.data;
            const ok = d.isExecutionSuccess !== false;
            const res = { id: inst.id, name: inst.name, ok, body: d.body };
            if (!ok) res.error = (d.pluginErrorDetails && d.pluginErrorDetails.downstreamErrorMessage) || (Array.isArray(d.messages) && d.messages.join("; ")) || null;
            out.push(res);
        }
        return out;
    }

    if (OP === "update") {
        const list = await listInstances();
        const out = [];
        for (const u of ARGS.updates) {
            const inst = findInstance(list, u.instance);
            if (!inst) { out.push({ instance: u.instance, error: "instance not found on this page" }); continue; }
            const r = await putInstance(inst, u.inputs || {});
            out.push(r.ok ? { id: inst.id, name: inst.name, inputs: { ...(inst.inputs || {}), ...(u.inputs || {}) } } : { id: inst.id, error: r.error });
        }
        refresh();
        return out;
    }

    if (OP === "delete") {
        const list = await listInstances();
        const cw = store.getState().entities.canvasWidgets || {};
        const out = [];
        const removedIds = [];
        for (const ref of ARGS.instances) {
            const inst = findInstance(list, ref);
            if (!inst) { out.push({ instance: ref, error: "instance not found on this page" }); continue; }
            if (inst.type === "UI_MODULE") {
                const w = Object.values(cw).find(x => x.widgetName === inst.name);
                if (w) {
                    store.dispatch({ type: "WIDGET_DELETE", payload: { widgetId: w.widgetId, parentId: w.parentId, disallowUndo: true } });
                    removedIds.push(w.widgetId);
                }
            }
            const r = await api("DELETE", `/api/v1/moduleInstances/${inst.id}`);
            // A UI instance may already be gone (the widget deletion removes it) — that's fine.
            const gone = r.ok || !findInstance(await listInstances(), inst.id);
            out.push(gone ? { id: inst.id, name: inst.name, deleted: true } : { id: inst.id, error: r.error });
        }
        if (removedIds.length) {
            const p = await __persistLayout({ removedIds });
            if (!p.persisted) out.push({ error: p.error });
        }
        refresh();
        return out;
    }

    if (OP === "pull") {
        // The pull of a big app can take longer than the 60 s BiDi call: the POST runs in the tab and its
        // answer (with the server error message) is kept in window.__l360Pull. Calling again returns it.
        const guardado = window.__l360Pull;
        if (guardado && guardado.appId === appId && guardado.done) {
            window.__l360Pull = null;
            return { ...guardado.result, after: await pullStatus(),
                note: "result of the pull started earlier in this tab; refresh_page to load new versions" };
        }
        if (guardado && guardado.appId === appId && !guardado.done)
            return { pending: true, startedAt: guardado.startedAt, status: await pullStatus(),
                note: "pull still running in this tab; call again later (do not reload the page)" };
        const before = await pullStatus();
        if (before !== "UPGRADABLE") return { before, upToDate: before === "UPGRADED" || before === null, note: "nothing to update" };
        const corrida = { appId, done: false, startedAt: new Date().toISOString(), result: null };
        window.__l360Pull = corrida;
        const pedido = api("POST", `/api/v1/packages/${appId}/pull?requestPageId=${pageId}`)
            .then(r => { corrida.result = r.ok
                ? { before, ok: true, status: r.status, instancesUpdated: ((r.data && r.data.moduleInstances) || []).length }
                : { before, ok: false, status: r.status, error: r.error }; })
            .catch(e => { corrida.result = { before, ok: false, error: String(e && e.message || e) }; })
            .finally(() => { corrida.done = true; });
        const rapido = await Promise.race([pedido.then(() => true), sleep(45000).then(() => false)]);
        if (rapido) { window.__l360Pull = null; return { ...corrida.result, after: await pullStatus(),
            note: "refresh_page so the editor loads the new module versions" }; }
        return { pending: true, startedAt: corrida.startedAt, status: await pullStatus(),
            note: "pull still running in this tab; call update_app_packages again later (do not reload the page)" };
    }

    return { error: `unknown op ${OP}` };
})()
