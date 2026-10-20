(() => {
    // The page/artboard background. MainContainer.backgroundColor is often "none"/unset (the app
    // then shows the theme's background), so also return the theme background and the effective one.
    const s = window.__store.getState();
    const main = (s.entities.canvasWidgets || {})["0"] || {};
    const themeBg = s.ui.appTheming?.selectedTheme?.properties?.colors?.backgroundColor ?? null;
    const mainBg = main.backgroundColor ?? null;
    const effective = (mainBg && mainBg !== "none") ? mainBg : themeBg;
    return { mainContainerBackground: mainBg, themeBackground: themeBg, effective };
})()
