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
  qualificationStatus: 'approved',
  name: '张小明',
  phone: '138****1028'
};

test('account profile exposes approved identity and account state', () => {
  const view = getAccountProfileView(approvedDoctor);

  assert.equal(view.identityDisplay, '北京鲁泰合作医生');
  assert.equal(view.identityLabel, '鲁泰医生');
  assert.equal(view.qualificationLabel, '审核通过');
  assert.equal(view.qualificationIcon, 'passed');
  assert.equal(view.wechatBound, '已绑定');
});

test('account profile maps non-approved qualification states accurately', () => {
  const rejected = getAccountProfileView(Object.assign({}, approvedDoctor, {
    qualificationStatus: 'rejected'
  }));

  assert.equal(rejected.qualificationLabel, '审核未通过');
  assert.equal(rejected.qualificationTone, 'red');
  assert.equal(rejected.qualificationIcon, 'warning-o');
});

test('account profile requires editable identity fields', () => {
  const form = createAccountProfileForm(approvedDoctor);

  assert.equal(validateAccountProfile(form).valid, true);
  assert.equal(
    validateAccountProfile(Object.assign({}, form, { name: '' })).field,
    'name'
  );
  assert.equal(
    validateAccountProfile(Object.assign({}, form, { organization: '' })).field,
    'organization'
  );
});

test('account profile save preserves role and updates editable data', () => {
  const updated = saveAccountProfile(
    approvedDoctor,
    {
      name: '李医生',
      organization: '北京鲁泰服务有限公司',
      avatar: 'wxfile://avatar.png'
    },
    '139****6688'
  );

  assert.equal(updated.role, 'collaborator');
  assert.equal(updated.name, '李医生');
  assert.equal(updated.phone, '139****6688');
  assert.equal(updated.avatar, 'wxfile://avatar.png');
});
