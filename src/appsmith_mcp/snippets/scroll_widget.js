(() => {
    // Scroll a widget into view (through Appsmith's internal scroll containers too) and return its
    // viewport rect, so capture_screenshot can bring an off-screen widget on-screen and/or clip to
    // just it. devicePixelRatio is returned so the caller can scale the clip box if needed.
    const el = document.querySelector(`.appsmith_widget_${WIDGET_ID}`) || document.getElementById(WIDGET_ID);
    if (!el) return { error: `widget ${WIDGET_ID} not found in DOM (is it on the current page and not inside a closed modal/inactive tab?)` };
    el.scrollIntoView({ block: "center", inline: "center" });
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height, dpr: window.devicePixelRatio || 1 };
})()
