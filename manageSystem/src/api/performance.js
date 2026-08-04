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
}
