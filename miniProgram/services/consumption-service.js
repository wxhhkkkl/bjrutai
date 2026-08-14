const { request } = require('./request-service')
function getOverview(month) { return request('/api/v1/contributions/overview', { data: { month } }) }
function getTrend(period = '6m') { return request('/api/v1/contributions/trend', { data: { period } }) }
function listBills(options = {}) { const data = {}; ['month', 'status', 'cursor', 'pageSize'].forEach((key) => { if (options[key] !== undefined && options[key] !== '') data[key] = options[key] }); return request('/api/v1/contributions', { data: Object.keys(data).length ? data : undefined }) }
module.exports = { getOverview, getTrend, listBills }
