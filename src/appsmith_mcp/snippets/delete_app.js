(() => {
    window.__store.dispatch({
        type: "DELETE_APPLICATION_INIT",
        payload: { applicationId: APP_ID },
    });
    return { dispatched: true, applicationId: APP_ID };
})()
