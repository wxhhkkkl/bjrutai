const {
  DEFAULT_ORGANIZATION
} = require('./auth-onboarding');
const {
  normalizeIdentityType
} = require('./collaborator');

const DEFAULT_AVATAR = '/assets/images/profile-avatar.png';

function createAccountProfileForm(session) {
  const value = session || {};

  return {
    name: value.name || '张小明',
    organization: value.organization || DEFAULT_ORGANIZATION,
    avatar: value.avatar || DEFAULT_AVATAR
  };
}

function getIdentityDisplay(session) {
  const identityType = normalizeIdentityType(session);

  if (identityType === 'doctor') return '北京儒泰合作医生';
  if (identityType === 'promoter') return '北京儒泰市场拓展人';
  return '北京儒泰协作人员';
}

function getIdentityLabel(session) {
  const identityType = normalizeIdentityType(session);

  if (identityType === 'doctor') return '儒泰医生';
  if (identityType === 'promoter') return '市场拓展人';
  return '儒泰协作人员';
}

function getAccountProfileView(session) {
  const value = session || {};

  return {
    identityDisplay: getIdentityDisplay(value),
    identityLabel: getIdentityLabel(value),
    phone: value.phone || '138****1028',
    accountId: value.accountId || 'RT****4826',
    wechatBound: value.userId ? '已绑定' : '未绑定'
  };
}

function validateAccountProfile(form) {
  const value = form || {};

  if (!String(value.name || '').trim()) {
    return {
      valid: false,
      field: 'name',
      message: '请输入真实姓名'
    };
  }

  return {
    valid: true
  };
}

function saveAccountProfile(session, form, phone) {
  const value = session || {};

  return Object.assign({}, value, {
    name: String(form.name).trim(),
    organization: value.organization || DEFAULT_ORGANIZATION,
    avatar: form.avatar || DEFAULT_AVATAR,
    phone: phone || value.phone || '138****1028',
    phoneAuthorized: true,
    profileCompleted: true
  });
}

module.exports = {
  DEFAULT_AVATAR,
  createAccountProfileForm,
  getIdentityDisplay,
  getIdentityLabel,
  getAccountProfileView,
  validateAccountProfile,
  saveAccountProfile
};
