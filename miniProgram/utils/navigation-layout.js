const DEFAULT_NAVIGATION = Object.freeze({
  menuTop: 24,
  menuHeight: 32,
  bottomGap: 4,
  rightInset: 96
});

function calculateNavigationLayout(windowInfo = {}, menu = {}) {
  if (!menu.height || !menu.left) {
    return { ...DEFAULT_NAVIGATION };
  }

  const windowWidth = windowInfo.windowWidth || 375;
  const statusBarHeight = windowInfo.statusBarHeight || 20;

  return {
    menuTop: menu.top,
    menuHeight: menu.height,
    bottomGap: Math.max(menu.top - statusBarHeight, 4),
    rightInset: Math.max(windowWidth - menu.left + 8, 0)
  };
}

function getNavigationLayout(wxApi) {
  const api = wxApi || (typeof wx !== 'undefined' ? wx : null);

  if (!api || !api.getMenuButtonBoundingClientRect) {
    return { ...DEFAULT_NAVIGATION };
  }

  try {
    const windowInfo = api.getWindowInfo
      ? api.getWindowInfo()
      : api.getSystemInfoSync();
    const menu = api.getMenuButtonBoundingClientRect();

    return calculateNavigationLayout(windowInfo, menu);
  } catch (error) {
    return { ...DEFAULT_NAVIGATION };
  }
}

module.exports = {
  DEFAULT_NAVIGATION,
  calculateNavigationLayout,
  getNavigationLayout
};
