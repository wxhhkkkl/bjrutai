const { request } = require('./request-service')
const { formatChinaDateTime } = require('../utils/date-time')

function resolveInviteImageUrl(invite, apiBase) {
  if (!invite || !invite.refToken) return invite && invite.qrImageUrl
  const base = String(apiBase || '').trim().replace(/\/+$/, '')
  if (!base) return invite.qrImageUrl
  return `${base}/api/v1/staff-invite-codes/${encodeURIComponent(invite.refToken)}/image`
}

function formatInviteExpiry(value) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  // Older backend responses omitted the timezone while storing UTC.
  const withTimezone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`
  return formatChinaDateTime(withTimezone)
}

function normalizeInvite(invite) {
  if (!invite) return invite
  const app = typeof getApp === 'undefined' ? null : getApp()
  const apiBase = app && app.globalData ? app.globalData.apiBase : ''
  return {
    ...invite,
    qrImageUrl: resolveInviteImageUrl(invite, apiBase),
    expiresAtDisplay: formatInviteExpiry(invite.expiresAt)
  }
}

function getMyInviteCode() {
  return request('/api/v1/staff-invite-code').then(normalizeInvite)
}

function refreshMyInviteCode() {
  return request('/api/v1/staff-invite-code/refresh', { method: 'POST' }).then(normalizeInvite)
}

function revokeMyInviteCode() {
  return request('/api/v1/staff-invite-code/revoke', { method: 'POST' })
}

function getInviteInfo(refToken) {
  return request(`/api/v1/staff-invite-codes/${encodeURIComponent(refToken)}`, {
    auth: false,
    retryAfterRefresh: false
  })
}

function joinOrganization(refToken, data) {
  return request(`/api/v1/staff-invite-codes/${encodeURIComponent(refToken)}/join`, {
    method: 'POST',
    auth: false,
    retryAfterRefresh: false,
    data
  })
}

module.exports = {
  getMyInviteCode,
  refreshMyInviteCode,
  revokeMyInviteCode,
  getInviteInfo,
  joinOrganization,
  resolveInviteImageUrl,
  formatInviteExpiry
}
