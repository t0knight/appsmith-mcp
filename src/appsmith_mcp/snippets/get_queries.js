(() => {
    // Symmetric to get_js_objects: return each query's full actionConfiguration (httpMethod,
    // path, headers, body, pluginSpecifiedTemplates, formData) so a query can be *read* and
    // replicated, not just listed. Pass IDS to filter; empty/absent returns them all.
    const actions = window.__store.getState().entities.actions || [];
    const plugins = window.__store.getState().entities.plugins?.list || [];
    const sensitiveHeaders = new Set(["authorization", "proxy-authorization", "apikey", "x-api-key"]);
    const redactLiteralHeaders = value => {
        if (Array.isArray(value)) return value.map(redactLiteralHeaders);
        if (!value || typeof value !== "object") return value;
        const isSensitiveHeader = typeof value.key === "string"
            && sensitiveHeaders.has(value.key.trim().toLowerCase());
        const out = {};
        for (const [key, child] of Object.entries(value)) {
            out[key] = isSensitiveHeader
                && key === "value"
                && typeof child === "string"
                && child.trim()
                && !(child.includes("{{") && child.includes("}}"))
                ? "[REDACTED]"
                : redactLiteralHeaders(child);
        }
        return out;
    };
    const wanted = (Array.isArray(IDS) && IDS.length) ? new Set(IDS) : null;
    return actions
        .filter(a => a.config && (!wanted || wanted.has(a.config.id)))
        .map(a => {
            const c = a.config;
            return {
                id: c.id,
                name: c.name,
                pageId: c.pageId,
                pluginId: c.pluginId,
                pluginType: c.pluginType,
                pluginPackageName: plugins.find(p => p.id === c.pluginId)?.packageName,
                datasourceId: c.datasource && c.datasource.id,
                datasourceName: c.datasource && c.datasource.name,
                // Embedded (inline-URL) datasources have no id; expose the URL so callers can
                // tell which host the query really hits.
                datasourceUrl: c.datasource && c.datasource.datasourceConfiguration
                    && c.datasource.datasourceConfiguration.url,
                actionConfiguration: redactLiteralHeaders(c.actionConfiguration),
                runBehaviour: c.runBehaviour,
                confirmBeforeExecute: c.confirmBeforeExecute,
                executeOnLoad: c.executeOnLoad,
            };
        });
})()
