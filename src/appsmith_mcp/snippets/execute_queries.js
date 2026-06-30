(async () => {
    const xsrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('XSRF-TOKEN='))?.slice('XSRF-TOKEN='.length) || '');
    const out = [];
    for (const id of ACTION_IDS) {
        const formData = new FormData();
        formData.append('executeActionDTO', JSON.stringify({
            actionId: id, viewMode: false, paramProperties: {},
        }));
        const r = await fetch('/api/v1/actions/execute', {
            method: 'POST', credentials: 'include',
            headers: { 'X-XSRF-TOKEN': xsrf },
            body: formData,
        });
        const j = await r.json();
        out.push({
            id,
            ok: !!j.responseMeta?.success,
            statusCode: j.data?.statusCode,
            isExecutionSuccess: j.data?.isExecutionSuccess,
            body: j.data?.body,
        });
    }
    return out;
})()
