const { request } = require('./request-service')

function getCodeInfo(refToken) {
  return request(`/api/v1/customer-binding-codes/${encodeURIComponent(refToken)}`, {
    auth: false,
    retryAfterRefresh: false
  })
}

function claimCustomer(refToken, data) {
  return request(`/api/v1/customer-binding-codes/${encodeURIComponent(refToken)}/claim`, {
    method: 'POST',
    auth: false,
    retryAfterRefresh: false,
    data
  })
}

function claimWithSession(refToken) {
  return request(`/api/v1/customer-binding-codes/${encodeURIComponent(refToken)}/claim-session`, {
    method: 'POST',
    data: { consentConfirmed: true }
  })
}

module.exports = { getCodeInfo, claimCustomer, claimWithSession }
