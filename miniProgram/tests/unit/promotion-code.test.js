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
  assert.equal(profile.statusLabel, '客户绑定码可用');
  assert.equal(profile.sourceCity, '北京');
});

test('promotion instructions preserve the approved three-step flow', () => {
  assert.deepEqual(
    PROMOTION_STEPS.map((item) => item.id),
    ['scan', 'open', 'confirm']
  );
});

test('customer binding share carries the salesperson token without a title', () => {
  const profile = { name: '张小明', refToken: 'customer-token', qrImage: '/qr.png' };
  const share = createPromotionShare(profile);

  assert.equal('title' in share, false);
  assert.equal(
    share.path,
    '/pages/patient-binding/index?refToken=customer-token'
  );
  assert.equal(share.imageUrl, '/qr.png');
});

test('promotion share omits custom invitation copy and preserves path', () => {
  const share = createPromotionShare({ name: '张小明', shareTitle: '进入儒泰', sharePath: '/pages/index/index?source=BJTR&ref_token=token', qrImage: '/qr.png' });
  assert.equal('title' in share, false);
  assert.equal(share.path, '/pages/index/index?source=BJTR&ref_token=token');
  assert.equal(share.imageUrl, '/qr.png');
});
