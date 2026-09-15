const IDENTITY_LABELS = {
  doctor: '儒泰医生',
  promoter: '业务员',
  orgAdmin: '推广员（组织管理员）',
  personal: '普通用户',
  unknown: '儒泰医联人员'
};

function normalizeIdentityType(session) {
  const value = session || {};

  if (value.hasBusinessMembership === false || value.role === 'personal') {
    return 'personal';
  }

  if (value.orgRole === 'admin') return 'orgAdmin';

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

  if (role === 'personal') return 'personal';

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
  const hasMembership = value.hasBusinessMembership === true || (
    value.hasBusinessMembership !== false && collaborator
  );
  const active = value.activationStatus === 'active' &&
    value.membershipStatus !== 'disabled' &&
    value.orgStatus !== 'disabled';
  const businessReady = collaborator && hasMembership && active;

  return {
    promotion: businessReady,
    customerBinding: businessReady,
    contribution: businessReady,
    customerAnalysis: businessReady,
    // US5: org performance is visible only to org admins (backend-authorized).
    orgPerformance: businessReady && value.orgRole === 'admin',
    staffInvite: businessReady && value.orgRole === 'admin'
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
