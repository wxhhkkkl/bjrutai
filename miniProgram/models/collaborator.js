const IDENTITY_LABELS = {
  doctor: '鲁泰医生',
  promoter: '市场拓展人',
  unknown: '鲁泰协作人员'
};

function normalizeIdentityType(session) {
  const value = session || {};

  if (value.identityType === 'doctor' || value.identityType === 'promoter') {
    return value.identityType;
  }

  if (value.role === 'doctor' || value.role === 'promoter') {
    return value.role;
  }

  if (value.role === 'distributor') {
    return 'promoter';
  }

  return 'unknown';
}

function normalizeCollaboratorRole(session) {
  const role = session && session.role;

  if (
    role === 'collaborator' ||
    role === 'doctor' ||
    role === 'promoter' ||
    role === 'distributor'
  ) {
    return 'collaborator';
  }

  return 'unknown';
}

function getIdentityLabel(session) {
  return IDENTITY_LABELS[normalizeIdentityType(session)];
}

function getCollaboratorCapabilities(session) {
  // Business capability gating no longer depends on a personal qualification
  // status — the org qualification (FR-008) is enforced server-side. Only the
  // collaborator role and account activation gate feature access.
  const value = session || {};
  const collaborator = normalizeCollaboratorRole(value) === 'collaborator';
  const active = value.activationStatus === 'active';

  return {
    promotion: collaborator && active,
    customerBinding: collaborator && active,
    contribution: collaborator && active,
    customerAnalysis: collaborator && active,
    // US5: org performance is visible only to org admins (backend-authorized).
    orgPerformance: collaborator && active && value.orgRole === 'admin'
  };
}

function hasCapability(session, capability) {
  if (!capability) return true;
  return getCollaboratorCapabilities(session)[capability] === true;
}

module.exports = {
  IDENTITY_LABELS,
  normalizeIdentityType,
  normalizeCollaboratorRole,
  getIdentityLabel,
  getCollaboratorCapabilities,
  hasCapability
};
