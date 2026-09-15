const test = require('node:test');
const assert = require('node:assert/strict');
const {
  validateLoginAuthorization,
  validateLoginConsent,
  createPendingProfileSession,
  createProfileForm,
  validateProfileForm,
  completeProfileSession
} = require('../../models/auth-onboarding');

test('login authorization requires agreement and phone access', () => {
  assert.equal(
    validateLoginAuthorization({
      agreed: false,
      phoneAuthorized: false
    }).field,
    'agreement'
  );
  assert.equal(
    validateLoginAuthorization({
      agreed: true,
      phoneAuthorized: false
    }).field,
    'phone'
  );
  assert.equal(
    validateLoginAuthorization({
      agreed: true,
      phoneAuthorized: true
    }).ok,
    true
  );
});

test('credential login requires agreement but not prior WeChat phone access', () => {
  assert.equal(validateLoginConsent({ agreed: false, phoneAuthorized: false }).field, 'agreement');
  assert.equal(validateLoginConsent({ agreed: true, phoneAuthorized: false }).ok, true);
});

test('pending login session enters profile setup', () => {
  const session = createPendingProfileSession('138****1028');

  assert.equal(session.profileCompleted, false);
  assert.equal(session.role, 'personal');
  assert.equal(session.phoneAuthorized, true);
});

test('profile form validates required values and confirmation', () => {
  assert.equal(createProfileForm().name, '');
  assert.equal(createProfileForm({ name: '微信用户' }).name, '');
  assert.equal(createProfileForm({ name: '李明' }).name, '李明');
  assert.equal(
    validateProfileForm({
      name: '',
      organization: '北京儒泰服务有限公司'
    }, true).field,
    'name'
  );
  assert.equal(
    validateProfileForm(createProfileForm(), false).field,
    'name'
  );
  assert.equal(
    validateProfileForm({ name: '李明', organization: '' }, false).field,
    'confirmation'
  );
  assert.equal(
    validateProfileForm({ name: '张小明', organization: '' }, true).ok,
    true
  );
});

test('completed onboarding preserves the server-authorized identity', () => {
  const session = completeProfileSession(
    createPendingProfileSession(),
    {
      name: ' 张小明 ',
      organization: ' 北京儒泰服务有限公司 '
    }
  );

  assert.equal(session.profileCompleted, true);
  assert.equal(session.name, '张小明');
  assert.equal(session.role, 'personal');
  assert.equal(session.organization, '暂未加入组织');
});
