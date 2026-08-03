const { getDemoSession } = require('../mock/demo-control')
const {
  normalizeIdentityType,
  normalizeCollaboratorRole
} = require('../models/collaborator')

function normalizeSession(raw) {
  const session = raw || {}
  return {
    userId: session.userId || '', role: normalizeCollaboratorRole(session), identityType: normalizeIdentityType(session),
    activationStatus: session.activationStatus || 'inactive',
    orgRole: session.orgRole || 'member',
    profileCompleted: session.profileCompleted === true, name: session.name || '',
    phoneAuthorized: session.phoneAuthorized === true, phone: session.phone || '', organization: session.organization || '',
    avatar: session.avatar || ''
  }
}

function getEntry(session) {
  const value = normalizeSession(session)
  if (!value.userId || value.role === 'unknown') return { type: 'reLaunch', url: '/pages/auth/login/index' }
  if (!value.profileCompleted) return { type: 'reLaunch', url: '/pages/auth/profile-setup/index' }
  if (value.activationStatus === 'inactive') return { type: 'reLaunch', url: '/pages/common/feature-placeholder/index?title=账号未激活' }
  return { type: 'switchTab', url: '/pages/home/index' }
}

function getCurrentSession() { return normalizeSession(getDemoSession()) }
module.exports = { normalizeSession, getEntry, getCurrentSession }
