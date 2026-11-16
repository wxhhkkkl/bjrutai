const { request } = require('./request-service')

// This endpoint is the unified consumption aggregate; settlement/frozen commission state is read separately.
function requestOrgPerformance({ month } = {}) {
  return request('/api/v1/org/performance', {
    data: month ? { month } : undefined
  })
}

module.exports = {
  requestOrgPerformance
}
