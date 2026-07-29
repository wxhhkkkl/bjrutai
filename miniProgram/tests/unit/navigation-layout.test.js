const test = require('node:test');
const assert = require('node:assert/strict');
const {
  DEFAULT_NAVIGATION,
  calculateNavigationLayout,
  getNavigationLayout
} = require('../../utils/navigation-layout');

test('navigation aligns with a standard iPhone capsule', () => {
  const layout = calculateNavigationLayout(
    { windowWidth: 375, statusBarHeight: 20 },
    { top: 24, height: 32, left: 278 }
  );

  assert.deepEqual(layout, {
    menuTop: 24,
    menuHeight: 32,
    bottomGap: 4,
    rightInset: 105
  });
});

test('navigation follows a Dynamic Island capsule', () => {
  const layout = calculateNavigationLayout(
    { windowWidth: 393, statusBarHeight: 54 },
    { top: 59, height: 32, left: 296 }
  );

  assert.deepEqual(layout, {
    menuTop: 59,
    menuHeight: 32,
    bottomGap: 5,
    rightInset: 105
  });
});

test('navigation uses a stable fallback when system metrics are unavailable', () => {
  assert.deepEqual(
    getNavigationLayout({}),
    { ...DEFAULT_NAVIGATION }
  );
});
