const { request } = require('./request-service')

let activeUserId = ''
let inFlight = Object.create(null)

function normalizeUserId(userId) {
  return String(userId || '')
}

function resetForUser(userId) {
  const nextUserId = normalizeUserId(userId)
  if (nextUserId === activeUserId) return
  activeUserId = nextUserId
  inFlight = Object.create(null)
}

function sharedRequest(userId, key, loader) {
  resetForUser(userId)
  if (inFlight[key]) return inFlight[key]

  const promise = Promise.resolve()
    .then(loader)
    .finally(() => {
      if (inFlight[key] === promise) delete inFlight[key]
    })
  inFlight[key] = promise
  return promise
}

function getWorkbench(userId) {
  return sharedRequest(userId, 'workbench', () => request('/api/v1/workbench'))
}

function getNotices(userId) {
  return sharedRequest(userId, 'notices', () => request('/api/v1/workbench/notices'))
}

function getRecentBindings(userId) {
  return sharedRequest(userId, 'recent-bindings', () => request('/api/v1/workbench/recent-bindings'))
}

function getContributionSummary(month, userId) {
  const normalizedMonth = String(month || '')
  return sharedRequest(userId, `contribution-summary:${normalizedMonth}`, () => request(
    '/api/v1/workbench/contribution-summary',
    { data: normalizedMonth ? { month: normalizedMonth } : undefined }
  ))
}

function getAccountSummary(userId) {
  return sharedRequest(userId, 'account-summary', () => request('/api/v1/me/account-summary'))
}

function clearWorkbenchRequests() {
  activeUserId = ''
  inFlight = Object.create(null)
}

module.exports = {
  getWorkbench,
  getNotices,
  getRecentBindings,
  getContributionSummary,
  getAccountSummary,
  clearWorkbenchRequests
}
