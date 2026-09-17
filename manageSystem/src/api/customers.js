import http from './http'

// Backend envelope: { code, message, data, requestId, serverTime }
function payload(res) {
  return res.data && res.data.data !== undefined ? res.data.data : res.data
}

export const adminCustomerApi = {
  list(orgId, params = {}) {
    const query = { ...params }
    if (orgId) query.orgId = orgId
    return http.get('/admin/customers', { params: query }).then(payload)
  },
  export(orgId, params = {}) {
    return http.get('/admin/customers/export', {
      params: { orgId, ...params },
      responseType: 'blob',
    })
  },
  create(data) {
    return http.post('/admin/customers', data).then(payload)
  },
  detail(id) {
    return http.get(`/admin/customers/${id}`).then(payload)
  },
  update(id, data) {
    return http.patch(`/admin/customers/${id}`, data).then(payload)
  },
  transfer(id, data) {
    return http.post(`/admin/customers/${id}/transfer`, data).then(payload)
  },
  changeLogs(id) {
    return http.get(`/admin/customers/${id}/change-logs`).then(payload)
  },
}
