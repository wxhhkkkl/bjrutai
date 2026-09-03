import http from './http'

// Backend envelope: { code, message, data, requestId, serverTime }
function payload(res) {
  return res.data && res.data.data !== undefined ? res.data.data : res.data
}

export const contributionDashboardApi = {
  dashboard(params = {}) {
    return http.get('/admin/contributions/dashboard', { params }).then(payload)
  },
  orgsRanking(params = {}) {
    return http.get('/admin/contributions/rankings/orgs', { params }).then(payload)
  },
  personsRanking(params = {}) {
    return http.get('/admin/contributions/rankings/persons', { params }).then(payload)
  },
  bindingsRanking(params = {}) {
    return http.get('/admin/contributions/rankings/bindings', { params }).then(payload)
  },
  searchCustomers(params = {}) {
    return http.get('/admin/contributions/customers', { params }).then(payload)
  },
  createManual(data, idempotencyKey) {
    return http.post('/admin/contributions/manual', data, {
      headers: { 'Idempotency-Key': idempotencyKey },
    }).then(payload)
  },
}
