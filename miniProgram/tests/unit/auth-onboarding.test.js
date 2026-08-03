const test = require('node:test');
const assert = require('node:assert/strict');
const {
  validateLoginAuthorization,
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

test('pending login session enters profile setup', () => {
  const session = createPendingProfileSession('138****1028');

  assert.equal(session.profileCompleted, false);
  assert.equal(session.role, 'collaborator');
  assert.equal(session.phoneAuthorized, true);
});

test('profile form validates required values and confirmation', () => {
  assert.equal(
    validateProfileForm({
      name: '',
      organization: '北京鲁泰服务有限公司'
    }, true).field,
    'name'
  );
  assert.equal(
    validateProfileForm(createProfileForm(), false).field,
    'confirmation'
  );
  assert.equal(
    validateProfileForm(createProfileForm(), true).ok,
    true
  );
});

test('completed onboarding persists business identity', () => {
  const session = completeProfileSession(
    createPendingProfileSession(),
    {
      name: ' 张小明 ',
      organization: ' 北京鲁泰服务有限公司 '
    }
  );

  assert.equal(session.profileCompleted, true);
  assert.equal(session.name, '张小明');
  assert.equal(session.organization, '北京鲁泰服务有限公司');
});
