const {
  normalizeIdentityType,
  normalizeCollaboratorRole
} = require('../models/collaborator')

const SESSION_KEY = 'lutai_real_session'
const ACCESS_TOKEN_KEY = 'lutai_access_token'
const REFRESH_TOKEN_KEY = 'lutai_refresh_token'
const memory = {}

function storageGet(key) {
  return typeof wx !== 'undefined' ? wx.getStorageSync(key) : memory[key]
}

function storageSet(key, value) {
  if (typeof wx !== 'undefined') wx.setStorageSync(key, value)
  else memory[key] = value
}

function storageRemove(key) {
  if (typeof wx !== 'undefined') wx.removeStorageSync(key)
  else delete memory[key]
}

function normalizeSession(raw) {
  const session = raw || {}
  return {
    userId: session.userId || '',
    distributorId: session.distributorId || '',
    role: normalizeCollaboratorRole(session),
    identityType: normalizeIdentityType(session),
    activationStatus: session.activationStatus || 'inactive',
    orgId: session.orgId || '',
    orgName: session.orgName || session.organization || '',
    orgRole: session.orgRole === 'admin' ? 'admin' : 'member',
    sourceChannel: session.sourceChannel || '',
    permissions: Array.isArray(session.permissions) ? session.permissions.slice() : [],
    profileCompleted: session.profileCompleted === true,
    name: session.name || '',
    phoneAuthorized: session.phoneAuthorized === true,
    phone: session.phone || '',
    organization: session.organization || session.orgName || '',
    avatar: session.avatar || session.avatarUrl || '',
    wechatBound: session.wechatBound === true
  }
}

function buildDistributorSession(user, distributor) {
  const u = user || {}
  const d = distributor || {}
  return normalizeSession({
    userId: String(u.userId || ''),
    distributorId: String(d.distributorId || ''),
    role: 'collaborator',
    identityType: 'promoter',
    activationStatus: u.activationStatus || (d.status === 'disabled' ? 'inactive' : 'active'),
    orgId: String(d.orgId || u.orgNodeId || ''),
    orgName: d.orgName || u.orgNodeName || '',
    orgRole: d.orgRole || u.orgRole || 'member',
    sourceChannel: d.sourceChannel || '',
    permissions: u.permissions || [],
    profileCompleted: Boolean(u.userId || d.distributorId),
    name: u.nickname || u.name || d.name || '',
    phone: u.phone || d.phone || '',
    organization: d.orgName || u.orgNodeName || '',
    avatar: u.avatarUrl || '',
    wechatBound: u.wechatBound === true
  })
}

function setSession(session) {
  storageSet(SESSION_KEY, normalizeSession(session))
}

function getCurrentSession() {
  return normalizeSession(storageGet(SESSION_KEY))
}

function setTokens(accessToken, refreshToken) {
  storageSet(ACCESS_TOKEN_KEY, accessToken || '')
  storageSet(REFRESH_TOKEN_KEY, refreshToken || '')
}

function getAccessToken() {
  return storageGet(ACCESS_TOKEN_KEY) || ''
}

function getRefreshToken() {
  return storageGet(REFRESH_TOKEN_KEY) || ''
}

function setAuthenticatedSession(value = {}) {
  setTokens(value.accessToken, value.refreshToken)
  setSession(value.session)
}

function clearAuthenticatedSession() {
  storageRemove(ACCESS_TOKEN_KEY)
  storageRemove(REFRESH_TOKEN_KEY)
  storageRemove(SESSION_KEY)
}

function getEntry(session) {
  const value = normalizeSession(session)
  if (!value.userId || value.role === 'unknown') {
    return { type: 'reLaunch', url: '/pages/auth/login/index' }
  }
  if (value.activationStatus === 'inactive') {
    return {
      type: 'reLaunch',
      url: '/pages/common/feature-placeholder/index?title=账号未激活'
    }
  }
  return { type: 'switchTab', url: '/pages/home/index' }
}

module.exports = {
  SESSION_KEY,
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  normalizeSession,
  getEntry,
  getCurrentSession,
  buildDistributorSession,
  setSession,
  setTokens,
  getAccessToken,
  getRefreshToken,
  setAuthenticatedSession,
  clearAuthenticatedSession
}
