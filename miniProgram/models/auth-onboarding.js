const DEFAULT_ORGANIZATION = '北京鲁泰服务有限公司';

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

function createPendingProfileSession(phone) {
  return {
    userId: 'wx-promoter-001',
    role: 'collaborator',
    identityType: 'promoter',
    activationStatus: 'active',
    profileCompleted: false,
    name: '微信用户',
    phoneAuthorized: true,
    phone: phone || '138****1028',
    organization: DEFAULT_ORGANIZATION
  };
}

function createProfileForm(session) {
  const value = session || {};

  return {
    name: value.name && value.name !== '微信用户'
      ? value.name
      : '张小明',
    organization: value.organization || DEFAULT_ORGANIZATION
  };
}

function validateProfileForm(form, confirmed) {
  const value = form || {};

  if (!String(value.name || '').trim()) {
    return {
      ok: false,
      field: 'name',
      message: '请输入真实姓名'
    };
  }

  if (!String(value.organization || '').trim()) {
    return {
      ok: false,
      field: 'organization',
      message: '请输入所属机构'
    };
  }

  if (!confirmed) {
    return {
      ok: false,
      field: 'confirmation',
      message: '请确认以上信息真实有效'
    };
  }

  return { ok: true };
}

function completeProfileSession(session, form) {
  return Object.assign({}, session || {}, {
    role: 'collaborator',
    identityType: session && session.identityType
      ? session.identityType
      : 'promoter',
    activationStatus: 'active',
    profileCompleted: true,
    name: String(form.name).trim(),
    organization: String(form.organization).trim()
  });
}

module.exports = {
  DEFAULT_ORGANIZATION,
  validateLoginAuthorization,
  createPendingProfileSession,
  createProfileForm,
  validateProfileForm,
  completeProfileSession
};
