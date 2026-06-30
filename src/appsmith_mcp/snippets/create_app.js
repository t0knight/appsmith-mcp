(() => {
    window.__store.dispatch({
        type: "CREATE_APPLICATION_INIT",
        payload: {
            applicationName: APP_NAME,
            workspaceId: WORKSPACE_ID,
            icon: ICON,
            color: COLOR,
        },
    });
    return { dispatched: true, workspaceId: WORKSPACE_ID, name: APP_NAME };
})()
