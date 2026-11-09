const { request } = require('./request-service')
function getOverview(month) { return request('/api/v1/contributions/overview', { data: { month } }) }
function getTrend(period = '6m') { return request('/api/v1/contributions/trend', { data: { period } }) }

function normalizeContributionItem(item) {
  if (!item || typeof item !== 'object') return item
  const sourceType = item.sourceType || (item.source === 'mall_order' ? 'mall_order' : 'legacy_bill')
  return { ...item, sourceType }
}

function normalizeContributionList(payload) {
  if (!payload || typeof payload !== 'object' || !Array.isArray(payload.items)) return payload
  return { ...payload, items: payload.items.map(normalizeContributionItem) }
}

function listBills(options = {}) {
  const data = {}
  ;['month', 'status', 'cursor', 'pageSize'].forEach((key) => {
    if (options[key] !== undefined && options[key] !== '') data[key] = options[key]
  })
  return request('/api/v1/contributions', {
    data: Object.keys(data).length ? data : undefined
  }).then(normalizeContributionList)
}
module.exports = { getOverview, getTrend, listBills }
