const test = require('node:test');
const assert = require('node:assert/strict');
const appConfig = require('../../app.json');
const {
  TAB_ITEMS,
  ACTION_TARGETS
} = require('../../models/navigation');

test('four tabs have unique routes', () => {
  assert.equal(TAB_ITEMS.length, 4);
  assert.equal(
    new Set(TAB_ITEMS.map((item) => item.pagePath)).size,
    4
  );
});

test('action routes point to registered mini program pages', () => {
  for (const action of Object.values(ACTION_TARGETS)) {
    const pagePath = action.path.split('?')[0].replace(/^\//, '');

    assert.ok(appConfig.pages.includes(pagePath), action.path);
  }
});

test('customer binding action opens the real three-step flow', () => {
  assert.equal(
    ACTION_TARGETS['bind-client'].path,
    '/pages/customer-binding/index'
  );
});

test('binding records action opens the real records page', () => {
  assert.equal(
    ACTION_TARGETS['binding-records'].path,
    '/pages/binding-records/index'
  );
});

test('customer analysis action opens the real analysis page', () => {
  assert.equal(
    ACTION_TARGETS['customer-analysis'].path,
    '/pages/customer-analysis/index'
  );
});

test('contribution detail action opens the real detail page', () => {
  assert.equal(
    ACTION_TARGETS['contribution-detail'].path,
    '/pages/contribution-detail/index'
  );
});

test('promotion code action opens the real share page', () => {
  assert.equal(
    ACTION_TARGETS['promote-code'].path,
    '/pages/promotion-code/index'
  );
});

test('account information action opens the real profile editor', () => {
  assert.equal(
    ACTION_TARGETS.profile.path,
    '/pages/account-profile/index'
  );
});

test('help and feedback action opens the real feedback form', () => {
  assert.equal(
    ACTION_TARGETS['help-feedback'].path,
    '/pages/help-feedback/index'
  );
});

test('article list is a public action shared by homepage and profile', () => {
  assert.deepEqual(ACTION_TARGETS['article-list'], {
    title: '文章资讯',
    path: '/pages/articles/index'
  });
  assert.ok(appConfig.pages.includes('pages/articles/index'));
  assert.ok(appConfig.pages.includes('pages/article-detail/index'));
});
