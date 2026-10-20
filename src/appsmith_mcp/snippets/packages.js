(async () => {
    // Package & module operations through the same endpoints the package editor uses.
    // OP: list | get | create | create_modules | update_module | publish | delete_package | delete_module.
    // ARGS: per-op input.
    const state = window.__store && window.__store.getState();
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
    // Workspace of what is open in the editor (app or package); null on the dashboard, where the
    // "selected" workspace is just whichever loaded first.
    const contextWorkspace = () => state?.ui?.applications?.currentApplication?.workspaceId
        || (state?.entities?.packages || {})[state?.ui?.editor?.currentPackageId]?.workspaceId
        || null;
    const workspaceId = () => ARGS.workspace_id || contextWorkspace() || state?.ui?.selectedWorkspace?.workspace?.id;
    const newId = () => Array.from({ length: 10 }, () => "abcdefghijklmnopqrstuvwxyz"[Math.floor(Math.random() * 26)]).join("");
    const bindRe = /\{\{[\s\S]*?\}\}/;
    const bindingPaths = (val, prefix = "", out = []) => {
        if (typeof val === "string") { if (bindRe.test(val)) out.push({ key: prefix }); }
        else if (Array.isArray(val)) val.forEach((v, i) => bindingPaths(v, `${prefix}[${i}]`, out));
        else if (val && typeof val === "object") for (const [k, v] of Object.entries(val)) bindingPaths(v, prefix ? `${prefix}.${k}` : k, out);
        return out;
    };
    const isUi = p => p.type === "UI";
    const editorUrl = (pkg, moduleId) => `${location.origin}/${isUi(pkg) ? "ui-pkg" : "pkg"}/${pkg.id}/${moduleId}/edit`;
    const summarizePackage = p => ({
        id: p.id, name: p.name, type: p.type, workspaceId: p.workspaceId, lastPublishedAt: p.lastPublishedAt || null,
        modifiedAt: p.modifiedAt || null, gitConnected: !!p.gitArtifactMetadata,
        ...(p.gitArtifactMetadata ? { gitRepo: p.gitArtifactMetadata.repoName, gitBranch: p.gitArtifactMetadata.branchName } : {}),
    });
    const children = form => (form || []).flatMap(s => s.children || []);
    // Keep existing field ids (by label) so instance input values stay attached to their field.
    const buildForm = (form, fields, kind) => {
        const section = (form && form[0]) || { id: newId(), sectionName: "", children: [] };
        const byLabel = Object.fromEntries(children(form).map(c => [c.label, c]));
        const kids = fields.map(f => {
            const prev = byLabel[f.name] || {};
            const base = { id: prev.id || newId(), label: f.name, propertyName: `${kind}.${f.name}`, controlType: "INPUT_TEXT" };
            return kind === "inputs" ? { ...base, defaultValue: f.default == null ? "" : String(f.default) } : { ...base, value: f.value == null ? "" : String(f.value) };
        });
        return [{ ...section, children: kids }];
    };
    const outputPaths = form => children(form).map((c, i) => (bindRe.test(String(c.value || "")) ? { key: `outputsForm[0].children[${i}].value` } : null)).filter(Boolean);
    const parseFunctions = body => {
        const names = [];
        const re = /^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*(?:\(|:\s*(?:async\s*)?(?:function\b|\())/gm;
        let m;
        while ((m = re.exec(body || ""))) if (!["if", "for", "while", "switch", "return", "export", "default"].includes(m[1]) && !names.includes(m[1])) names.push(m[1]);
        return names;
    };

    if (OP === "list") {
        const ws = ARGS.workspace_id || contextWorkspace();
        let workspaces = [{ id: ws, name: null }];
        if (!ws) {
            const h = await api("GET", "/api/v1/workspaces/home");
            if (!h.ok) return { error: h.error };
            workspaces = (h.data || []).map(w => ({ id: w.id, name: w.name }));
        }
        const out = [];
        for (const w of workspaces) {
            const r = await api("GET", `/api/v1/packages?workspaceId=${w.id}`);
            if (!r.ok) return { error: r.error };
            for (const p of r.data || []) out.push({ ...summarizePackage(p), ...(w.name ? { workspaceName: w.name } : {}) });
        }
        return out;
    }

    if (OP === "get") {
        const r = await api("GET", `/api/v1/packages/${ARGS.package_id}`);
        if (!r.ok) return { error: r.error };
        const pkg = r.data.packageData;
        return {
            package: summarizePackage(pkg),
            modules: (r.data.modules || []).map(m => ({
                id: m.id, name: m.name, type: m.type, moduleUUID: m.moduleUUID,
                inputs: children(m.inputsForm).map(c => ({ name: c.label, default: c.defaultValue })),
                outputs: children(m.outputsForm).map(c => ({ name: c.label, value: c.value })),
                editorUrl: editorUrl(pkg, m.id),
            })),
        };
    }

    const uiModuleBody = (name, inputs, outputs) => ({
        name, type: "UI_MODULE",
        layouts: [{ dsl: JSON.parse(JSON.stringify(DEFAULT_UI_DSL)), layoutOnLoadActions: [] }],
        inputsForm: buildForm(null, inputs || [], "inputs"),
        outputsForm: buildForm(null, outputs || [], "outputs"),
    });

    if (OP === "create") {
        const ws = workspaceId();
        if (!ws) return { error: "workspace not found — pass workspace_id" };
        const packageData = { name: ARGS.name, icon: "package", color: "#9747FF1A", type: ARGS.type };
        const r = ARGS.type === "UI"
            ? await api("POST", `/api/v1/packages/with-module?workspaceId=${ws}`, { packageData, defaultModule: uiModuleBody(ARGS.module_name || "UIModule1") })
            : await api("POST", `/api/v1/packages?workspaceId=${ws}`, { ...packageData, workspaceId: ws });
        if (!r.ok) return { error: r.error };
        return summarizePackage(r.data);
    }

    if (OP === "create_modules") {
        const out = [];
        // Read datasources/plugins from the API (the dashboard doesn't load them into the store).
        const pkgR = await api("GET", `/api/v1/packages/${ARGS.package_id}`);
        if (!pkgR.ok) return [{ error: pkgR.error }];
        const ws = pkgR.data.packageData.workspaceId;
        const dsList = (await api("GET", `/api/v1/datasources?workspaceId=${ws}`)).data || [];
        const plugins = (await api("GET", `/api/v1/plugins?workspaceId=${ws}`)).data || [];
        for (const m of ARGS.modules) {
            const type = String(m.type || "").toUpperCase();
            const inputsForm = buildForm(null, m.inputs || [], "inputs");
            let body;
            if (type === "QUERY") {
                const ds = dsList.find(d => d.id === m.datasource_id || d.name === m.datasource_id);
                if (!ds) { out.push({ name: m.name, error: `datasource ${m.datasource_id} not found in this workspace` }); continue; }
                const actionConfiguration = { ...(m.action_config || {}) };
                if (m.body != null) actionConfiguration.body = m.body;
                if (!actionConfiguration.pluginSpecifiedTemplates) actionConfiguration.pluginSpecifiedTemplates = [{ value: false }];
                body = { packageId: ARGS.package_id, name: m.name, type: "QUERY_MODULE", inputsForm,
                    entity: { type: "ACTION", name: m.name, pluginId: ds.pluginId, datasource: { id: ds.id },
                        actionConfiguration, dynamicBindingPathList: bindingPaths(actionConfiguration) } };
            } else if (type === "JS") {
                const js = plugins.find(p => p.type === "JS");
                const fns = m.function_names || parseFunctions(m.body);
                body = { packageId: ARGS.package_id, name: m.name, type: "JS_MODULE", inputsForm,
                    entity: { type: "JS_OBJECT", name: m.name, workspaceId: ws, pluginId: js && js.id, pluginType: "JS",
                        body: m.body || "export default {\n}", variables: [],
                        actions: fns.map(n => ({ name: n, workspaceId: ws, runBehaviour: "MANUAL", clientSideExecution: true,
                            actionConfiguration: { body: "", timeoutInMillisecond: 0, jsArguments: [] } })) } };
            } else if (type === "UI") {
                body = { packageId: ARGS.package_id, ...uiModuleBody(m.name, m.inputs, m.outputs) };
                body.dynamicBindingPathList = outputPaths(body.outputsForm);
            } else {
                out.push({ name: m.name, error: "type must be QUERY, JS or UI" });
                continue;
            }
            const r = await api("POST", "/api/v1/modules", body);
            out.push(r.ok ? { id: r.data.id, name: r.data.name, type: r.data.type, moduleUUID: r.data.moduleUUID } : { name: m.name, error: r.error });
        }
        return out;
    }

    if (OP === "update_module") {
        const g = await api("GET", `/api/v1/modules/${ARGS.module_id}`);
        if (!g.ok) return { error: g.error };
        const m = g.data;
        const res = { id: m.id, name: m.name };
        if (ARGS.inputs || ARGS.outputs) {
            const body = { ...m };
            delete body.layouts;  // the layout is saved through the module editor, never here
            if (ARGS.inputs) body.inputsForm = buildForm(m.inputsForm, ARGS.inputs, "inputs");
            if (ARGS.outputs) {
                body.outputsForm = buildForm(m.outputsForm, ARGS.outputs, "outputs");
                body.dynamicBindingPathList = [
                    ...(m.dynamicBindingPathList || []).filter(p => !/^outputsForm/.test(p.key)),
                    ...outputPaths(body.outputsForm),
                ];
            }
            const r = await api("PUT", `/api/v1/modules/${m.id}`, body);
            if (!r.ok) return { ...res, error: r.error };
            if (ARGS.inputs) res.inputs = ARGS.inputs.map(f => f.name);
            if (ARGS.outputs) res.outputs = ARGS.outputs.map(f => f.name);
        }
        if (ARGS.name && ARGS.name !== m.name) {
            // Renaming rewrites references, so it goes through the refactor endpoint.
            const r = await api("PUT", "/api/v1/modules/refactor", { moduleId: m.id, oldName: m.name, newName: ARGS.name });
            if (!r.ok) return { ...res, error: r.error };
            res.name = ARGS.name;
        }
        const cur = state?.ui?.editor?.currentModuleId;
        if (cur === m.id) res.note = "module editor open — refresh_page to see the new inputs/outputs/name in the editor";
        return res;
    }

    if (OP === "publish") {
        const g = await api("GET", `/api/v1/packages/${ARGS.package_id}`);
        if (!g.ok) return { error: g.error };
        const pkg = g.data.packageData;
        if (!CONFIRM) {
            return { error: `publishing ${pkg.name} updates every app that uses it on their next package update — call again with confirm=true after the user agrees`, package: summarizePackage(pkg) };
        }
        const r = await api("POST", `/api/v1/packages/${pkg.id}/publish`, {});
        if (!r.ok) return { error: r.error };
        const res = { package: pkg.name, published: !!r.data.status, lastPublishedVersion: r.data.lastPublishedVersion,
            next: "apps get it with update_app_packages (or the editor's update prompt)" };
        if (pkg.gitArtifactMetadata) res.warning = `package is connected to Git (${pkg.gitArtifactMetadata.repoName}) — commit the changes through Appsmith's Git panel`;
        return res;
    }

    // Deletion is irreversible; the confirm gate lives in server.py, which only dispatches
    // here once the caller has confirmed.
    if (OP === "delete_package" || OP === "delete_module") {
        const base = OP === "delete_package" ? "/api/v1/packages" : "/api/v1/modules";
        const out = [];
        for (const id of ARGS.ids || []) {
            const r = await api("DELETE", `${base}/${id}`);
            out.push(r.ok ? { id, ok: true } : { id, ok: false, error: r.error });
        }
        return out;
    }

    return { error: `unknown op ${OP}` };
})()
