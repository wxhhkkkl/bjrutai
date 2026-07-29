const IDENTITY_LABELS = {
  doctor: '鲁泰医生',
  promoter: '市场拓展人',
  unknown: '鲁泰协作人员'
};

const VALID_QUALIFICATION_STATES = ['approved', 'expiring'];

function normalizeIdentityType(session) {
  const value = session || {};

  if (value.identityType === 'doctor' || value.identityType === 'promoter') {
    return value.identityType;
  }

  if (value.role === 'doctor' || value.role === 'promoter') {
    return value.role;
  }

  return 'unknown';
}

function normalizeCollaboratorRole(session) {
  const role = session && session.role;

  if (
    role === 'collaborator' ||
    role === 'doctor' ||
    role === 'promoter'
  ) {
    return 'collaborator';
  }

  return 'unknown';
}

function getIdentityLabel(session) {
  return IDENTITY_LABELS[normalizeIdentityType(session)];
}

function getCollaboratorCapabilities(session) {
  const value = session || {};
  const collaborator = normalizeCollaboratorRole(value) === 'collaborator';
  const active = value.activationStatus === 'active';
  const qualified = VALID_QUALIFICATION_STATES.indexOf(
    value.qualificationStatus
  ) !== -1;

  return {
    qualification: collaborator,
    promotion: collaborator && active && qualified,
    customerBinding: collaborator && active && qualified,
    contribution: collaborator && active && qualified,
    customerAnalysis: collaborator && active && qualified
  };
}

function hasCapability(session, capability) {
  if (!capability) return true;
  return getCollaboratorCapabilities(session)[capability] === true;
}

module.exports = {
  IDENTITY_LABELS,
  VALID_QUALIFICATION_STATES,
  normalizeIdentityType,
  normalizeCollaboratorRole,
  getIdentityLabel,
  getCollaboratorCapabilities,
  hasCapability
};
