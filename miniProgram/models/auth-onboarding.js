const DEFAULT_ORGANIZATION = '暂未加入组织';

function validateLoginAuthorization(state) {
  const value = state || {};

  if (!value.agreed) {
    return {
      ok: false,
      field: 'agreement',
      message: '请先阅读并同意用户协议和隐私政策'
    };
  }

  if (!value.phoneAuthorized) {
    return {
      ok: false,
      field: 'phone',
      message: '请先授权手机号'
    };
  }

  return { ok: true };
}

// Login credentials are already supplied by the user. WeChat phone access is
// a separate binding capability and must not block phone + password login.
function validateLoginConsent(state) {
  const value = state || {};

  if (!value.agreed) {
    return {
      ok: false,
      field: 'agreement',
      message: '请先阅读并同意用户协议和隐私政策'
    };
  }

  return { ok: true };
}

function createPendingProfileSession(phone) {
  return {
    userId: 'wx-promoter-001',
    role: 'personal',
    identityType: 'personal',
    activationStatus: 'active',
    profileCompleted: false,
    name: '微信用户',
    phoneAuthorized: true,
    phone: phone || '138****1028',
    organization: DEFAULT_ORGANIZATION,
    hasBusinessMembership: false
  };
}

function createProfileForm(session) {
  const value = session || {};

  return {
    name: value.name && value.name !== '微信用户'
      ? value.name
      : '',
    organization: value.organization || DEFAULT_ORGANIZATION
  };
}

function validateProfileForm(form) {
  const value = form || {};

  if (!String(value.name || '').trim()) {
    return {
      ok: false,
      field: 'name',
      message: '请输入真实姓名'
    };
  }

  return { ok: true };
}

function completeProfileSession(session, form) {
  const value = session || {};

  return Object.assign({}, value, {
    role: value.role || 'personal',
    identityType: value.identityType || 'personal',
    activationStatus: 'active',
    profileCompleted: true,
    name: String(form.name).trim(),
    organization: value.organization || DEFAULT_ORGANIZATION
  });
}

module.exports = {
  DEFAULT_ORGANIZATION,
  validateLoginAuthorization,
  validateLoginConsent,
  createPendingProfileSession,
  createProfileForm,
  validateProfileForm,
  completeProfileSession
};
