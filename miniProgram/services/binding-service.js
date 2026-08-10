const { request } = require('./request-service')

function clean(values) {
  const result = {}
  Object.keys(values).forEach((key) => { if (values[key] !== undefined && values[key] !== '') result[key] = values[key] })
  return Object.keys(result).length ? result : undefined
}

function getSelectablePromoters(options = {}) {
  return request('/api/v1/promoters/selectable', { data: clean({ keyword: options.keyword, cursor: options.cursor, limit: options.limit }) })
}
function getLatestAgreements() { return request('/api/v1/agreements/latest') }
function recordConsent(values) {
  return request('/api/v1/consents', { method: 'POST', data: { agreementId: values.agreementId, scene: values.scene, confirmed: values.confirmed !== false, subjectType: values.subjectType || 'user' } })
}
function submitBinding(values, idempotencyKey) {
  return request('/api/v1/binding-requests', { method: 'POST', idempotencyKey, data: clean({ promoterId: values.promoterId, promoterCode: values.promoterCode, customerInfo: values.customerInfo, consentRecordId: values.consentRecordId, sourceType: values.sourceType || 'manual' }) })
}
function listBindingRequests(options = {}) {
  return request('/api/v1/binding-requests', { data: clean({ status: options.status, role: options.role || 'initiator', cursor: options.cursor, limit: options.limit, submittedByMe: options.submittedByMe, keyword: options.keyword, sortBy: options.sortBy || 'created_at', sortOrder: options.sortOrder || 'desc' }) })
}
function getBindingSummary() { return request('/api/v1/binding-summary') }
function getBindingRequest(id) { return request(`/api/v1/binding-requests/${encodeURIComponent(String(id))}`) }
function retryBindingRequest(id, idempotencyKey) { return request(`/api/v1/binding-requests/${encodeURIComponent(String(id))}/retry`, { method: 'POST', idempotencyKey }) }

module.exports = { getSelectablePromoters, getLatestAgreements, recordConsent, submitBinding, listBindingRequests, getBindingSummary, getBindingRequest, retryBindingRequest }
