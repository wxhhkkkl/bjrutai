const {
  DEFAULT_ORGANIZATION
} = require('./auth-onboarding');
const {
  normalizeIdentityType
} = require('./collaborator');

const DEFAULT_AVATAR = '/assets/images/profile-avatar.png';
const QUALIFICATION_LABELS = {
  approved: {
    label: '审核通过',
    tone: 'green',
    icon: 'passed'
  },
  reviewing: {
    label: '审核中',
    tone: 'blue',
    icon: 'clock-o'
  },
  rejected: {
    label: '审核未通过',
    tone: 'red',
    icon: 'warning-o'
  },
  expiring: {
    label: '即将到期',
    tone: 'orange',
    icon: 'clock-o'
  }
};

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

  if (identityType === 'doctor') return '北京鲁泰合作医生';
  if (identityType === 'promoter') return '北京鲁泰市场拓展人';
  return '北京鲁泰协作人员';
}

function getIdentityLabel(session) {
  const identityType = normalizeIdentityType(session);

  if (identityType === 'doctor') return '鲁泰医生';
  if (identityType === 'promoter') return '市场拓展人';
  return '鲁泰协作人员';
}

function getQualificationDisplay(status) {
  return QUALIFICATION_LABELS[status] || QUALIFICATION_LABELS.reviewing;
}

function getAccountProfileView(session) {
  const value = session || {};
  const qualification = getQualificationDisplay(value.qualificationStatus);

  return {
    identityDisplay: getIdentityDisplay(value),
    identityLabel: getIdentityLabel(value),
    phone: value.phone || '138****1028',
    accountId: value.accountId || 'RT****4826',
    wechatBound: value.userId ? '已绑定' : '未绑定',
    qualificationLabel: qualification.label,
    qualificationTone: qualification.tone,
    qualificationIcon: qualification.icon,
    qualificationStatus: QUALIFICATION_LABELS[value.qualificationStatus]
      ? value.qualificationStatus
      : 'reviewing'
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

  if (!String(value.organization || '').trim()) {
    return {
      valid: false,
      field: 'organization',
      message: '请输入所属机构'
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
    organization: String(form.organization).trim(),
    avatar: form.avatar || DEFAULT_AVATAR,
    phone: phone || value.phone || '138****1028',
    phoneAuthorized: true,
    profileCompleted: true
  });
}

module.exports = {
  DEFAULT_AVATAR,
  QUALIFICATION_LABELS,
  createAccountProfileForm,
  getIdentityDisplay,
  getIdentityLabel,
  getQualificationDisplay,
  getAccountProfileView,
  validateAccountProfile,
  saveAccountProfile
};
