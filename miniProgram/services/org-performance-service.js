const { request } = require('./request-service')

function requestOrgPerformance({ month } = {}) {
  return request('/api/v1/org/performance', {
    data: month ? { month } : undefined
  })
}

module.exports = {
  requestOrgPerformance
}
