const { request } = require('./request-service')

function cleanQuery(values) {
  const query = {}
  Object.keys(values).forEach((key) => {
    if (values[key] !== undefined && values[key] !== null && values[key] !== '') {
      query[key] = values[key]
    }
  })
  return Object.keys(query).length ? query : undefined
}

function listCustomers(options = {}) {
  return request('/api/v1/customers', {
    data: cleanQuery({
      status: options.status,
      keyword: options.keyword,
      cursor: options.cursor,
      pageSize: options.pageSize
    })
  })
}

function getCustomer(customerId) {
  return request(`/api/v1/customers/${encodeURIComponent(String(customerId))}`)
}

function patchCustomer(customerId, values = {}) {
  const data = {}
  ;['name', 'phone', 'note', 'familyPhone', 'changeReason'].forEach((field) => {
    if (values[field] !== undefined) data[field] = values[field]
  })
  return request(`/api/v1/customers/${encodeURIComponent(String(customerId))}`, {
    method: 'PATCH',
    data
  })
}

function getCustomerAnalysis(period = '30d') {
  return request('/api/v1/customer-analysis', { data: { period } })
}

function getServiceRecords(customerId, options = {}) { return request(`/api/v1/customers/${encodeURIComponent(String(customerId))}/service-records`, { data: cleanQuery(options) }) }
function getCustomerContributions(customerId, options = {}) { return request(`/api/v1/customers/${encodeURIComponent(String(customerId))}/contributions`, { data: cleanQuery(options) }) }
function createFollowup(customerId, data) { return request(`/api/v1/customers/${encodeURIComponent(String(customerId))}/followups`, { method: 'POST', data }) }
function saveFollowupDraft(customerId, data) { return request(`/api/v1/customers/${encodeURIComponent(String(customerId))}/followup-drafts`, { method: 'POST', data }) }

module.exports = {
  listCustomers,
  getCustomer,
  patchCustomer,
  getCustomerAnalysis,
  getServiceRecords,
  getCustomerContributions,
  createFollowup,
  saveFollowupDraft
}
