const test = require('node:test');
const assert = require('node:assert/strict');
const {
  PROMOTION_STEPS,
  getPromotionProfile,
  createPromotionShare
} = require('../../models/promotion-code');

test('promotion profile uses current promoter identity', () => {
  const profile = getPromotionProfile({
    userId: 'test-collaborator',
    role: 'collaborator',
    identityType: 'promoter',
    name: '测试推广人'
  });

  assert.equal(profile.name, '测试推广人');
  assert.equal(profile.statusLabel, '推广码可用');
  assert.equal(profile.sourceCity, '北京');
});

test('promotion instructions preserve the approved three-step flow', () => {
  assert.deepEqual(
    PROMOTION_STEPS.map((item) => item.id),
    ['scan', 'open', 'confirm']
  );
});

test('promotion share carries the promoter source', () => {
  const profile = getPromotionProfile({ name: '张小明' });
  const share = createPromotionShare(profile);

  assert.match(share.title, /张小明/);
  assert.equal(
    share.path,
    '/pages/home/index?sourceId=demo-collaborator-001'
  );
  assert.equal(share.imageUrl, '/assets/images/promotion-qr.jpg');
});

test('promotion share prefers the server-issued title and path', () => {
  const share = createPromotionShare({ name: '张小明', shareTitle: '进入儒泰', sharePath: '/pages/index/index?source=BJTR&ref_token=token', qrImage: '/qr.png' });
  assert.equal(share.title, '进入儒泰');
  assert.equal(share.path, '/pages/index/index?source=BJTR&ref_token=token');
  assert.equal(share.imageUrl, '/qr.png');
});
