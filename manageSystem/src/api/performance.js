import http from './http'

// Backend envelope: { code, message, data, requestId, serverTime }
function payload(res) {
  return res.data && res.data.data !== undefined ? res.data.data : res.data
}

export const performanceApi = {
  getRules(orgId) {
    return http.get(`/admin/orgs/${orgId}/performance-rules`).then(payload)
  },
  saveRule(orgId, ruleType, data) {
    return http.put(`/admin/orgs/${orgId}/performance-rules/${ruleType}`, data).then(payload)
  },
  history(orgId) {
    return http.get(`/admin/orgs/${orgId}/performance-rules/history`).then(payload)
  },
  applyToDescendants(orgId, ruleType) {
    return http.post(`/admin/orgs/${orgId}/performance-rules/${ruleType}/apply-to-descendants`).then(payload)
  },
  // 008 绩效计算
  estimates(period, orgId) {
    return http.get('/admin/performance/estimates', { params: { period, orgId } }).then(payload)
  },
  settlements(period) {
    return http.get('/admin/performance/settlements', { params: { period } }).then(payload)
  },
  review(period) {
    return http.post(`/admin/performance/settlements/${period}/review`).then(payload)
  },
  reject(period, reason) {
    return http.post(`/admin/performance/settlements/${period}/reject`, { reason }).then(payload)
  },
  recompute(period) {
    return http.post(`/admin/performance/settlements/${period}/recompute`).then(payload)
  },
  export(period) {
    return http.get(`/admin/performance/settlements/${period}/export`, { responseType: 'blob' })
  },
}
