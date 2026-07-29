const test = require('node:test');
const assert = require('node:assert/strict');
const {
  PRIVACY_DOCUMENTS,
  createPrivacySettings,
  getAuthorizationView,
  getPrivacyDocument
} = require('../../models/privacy-authorization');

test('privacy settings start from the approved safe defaults', () => {
  assert.deepEqual(createPrivacySettings(), {
    maskSensitive: true,
    personalized: false
  });
  assert.deepEqual(createPrivacySettings({ personalized: true }), {
    maskSensitive: true,
    personalized: true
  });
});

test('authorization view combines account and system permissions', () => {
  const view = getAuthorizationView({
    userId: 'demo-user',
    phone: '138****1028'
  }, {
    camera: true,
    album: true,
    customerMessage: false
  });

  assert.equal(view.wechatLabel, '已绑定');
  assert.equal(view.phoneLabel, '已授权');
  assert.equal(view.mediaLabel, '已授权');
  assert.equal(view.customerMessageLabel, '未授权');
});

test('privacy documents expose the four approved policy entries', () => {
  assert.equal(PRIVACY_DOCUMENTS.length, 4);
  assert.equal(getPrivacyDocument('privacy').title, '隐私政策');
  assert.equal(getPrivacyDocument('unsupported'), null);
});
