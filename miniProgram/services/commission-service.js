const { request } = require('./request-service')

function centsOr(value, fallback) {
  return Number.isSafeInteger(value) ? value : fallback
}

function normalizeCommissionItem(item) {
  if (!item || typeof item !== 'object') return item
  const normal = centsOr(item.normalCommissionCent, centsOr(item.commissionCent, 0))
  const adjustment = centsOr(item.confirmedAdjustmentCent, 0)
  return {
    ...item,
    commissionCent: centsOr(item.commissionCent, normal),
    normalCommissionCent: normal,
    confirmedAdjustmentCent: adjustment,
    appliedDebtCent: centsOr(item.appliedDebtCent, 0),
    // The confirmed adjustment already includes applied debt; never subtract it again.
    redeemableCent: centsOr(item.redeemableCent, Math.max(0, normal + adjustment)),
    pendingDebtCent: centsOr(item.pendingDebtCent, 0)
  }
}

function normalizeCommissionMonth(month, { confirmedHistory = false } = {}) {
  if (!month || typeof month !== 'object') return month
  const isFrozen = confirmedHistory || month.status === 'confirmed'
  const normalized = {
    ...month,
    isFrozen,
    isEstimate: month.status === 'estimate'
  }
  if (Object.prototype.hasOwnProperty.call(month, 'intraOrg')) {
    normalized.intraOrg = normalizeCommissionItem(month.intraOrg)
  }
  if (Object.prototype.hasOwnProperty.call(month, 'orgManagement')) {
    normalized.orgManagement = normalizeCommissionItem(month.orgManagement)
  }
  if (month.summary && typeof month.summary === 'object') {
    normalized.summary = normalizeCommissionItem(month.summary)
  }
  if (Array.isArray(month.members)) {
    normalized.members = month.members.map(normalizeCommissionItem)
  }
  return normalized
}

function normalizeCommissionResponse(payload = {}) {
  if (!payload || typeof payload !== 'object') return payload
  return {
    ...payload,
    currentMonth: normalizeCommissionMonth(payload.currentMonth),
    confirmed: Array.isArray(payload.confirmed)
      ? payload.confirmed.map((month) => normalizeCommissionMonth(month, { confirmedHistory: true }))
      : payload.confirmed
  }
}

function requestMyCommission({ month } = {}) {
  return request('/api/v1/my/performance/commission', {
    data: month ? { month } : undefined
  }).then(normalizeCommissionResponse)
}

function requestOrgCommission({ month } = {}) {
  return request('/api/v1/org/performance/commission', {
    data: month ? { month } : undefined
  }).then(normalizeCommissionResponse)
}

module.exports = {
  requestMyCommission,
  requestOrgCommission
}
