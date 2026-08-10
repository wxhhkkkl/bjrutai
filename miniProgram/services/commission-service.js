const { request } = require('./request-service')

function requestMyCommission({ month } = {}) {
  return request('/api/v1/my/performance/commission', {
    data: month ? { month } : undefined
  })
}

function requestOrgCommission({ month } = {}) {
  return request('/api/v1/org/performance/commission', {
    data: month ? { month } : undefined
  })
}

module.exports = {
  requestMyCommission,
  requestOrgCommission
}
