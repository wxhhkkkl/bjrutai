const test = require('node:test');
const assert = require('node:assert/strict');
const {
  createAccountProfileForm,
  getAccountProfileView,
  validateAccountProfile,
  saveAccountProfile
} = require('../../models/account-profile');

const approvedDoctor = {
  userId: 'demo-doctor-001',
  role: 'collaborator',
  identityType: 'doctor',
  name: '张小明',
  phone: '138****1028'
};

test('account profile exposes identity and account state', () => {
  const view = getAccountProfileView(approvedDoctor);

  assert.equal(view.identityDisplay, '北京儒泰合作医生');
  assert.equal(view.identityLabel, '儒泰医生');
  assert.equal(view.wechatBound, '已绑定');
});

test('account profile only requires an editable name', () => {
  const form = createAccountProfileForm(approvedDoctor);

  assert.equal(validateAccountProfile(form).valid, true);
  assert.equal(
    validateAccountProfile(Object.assign({}, form, { name: '' })).field,
    'name'
  );
  assert.equal(validateAccountProfile(Object.assign({}, form, { organization: '' })).valid, true);
});

test('account profile save preserves role and updates editable data', () => {
  const updated = saveAccountProfile(
    approvedDoctor,
    {
      name: '李医生',
      organization: '北京儒泰服务有限公司',
      avatar: 'wxfile://avatar.png'
    },
    '139****6688'
  );

  assert.equal(updated.role, 'collaborator');
  assert.equal(updated.name, '李医生');
  assert.equal(updated.organization, '北京儒泰服务有限公司');
  assert.equal(updated.phone, '139****6688');
  assert.equal(updated.avatar, 'wxfile://avatar.png');
});
