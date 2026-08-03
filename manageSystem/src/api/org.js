import http from './http'

// Backend envelope: { code, message, data, requestId, serverTime }
function payload(res) {
  return res.data && res.data.data !== undefined ? res.data.data : res.data
}

export const orgApi = {
  getTree() {
    return http.get('/admin/orgs').then(payload)
  },
  getSubtree(id) {
    return http.get(`/admin/orgs/${id}`).then(payload)
  },
  create(data) {
    return http.post('/admin/orgs', data).then(payload)
  },
  update(id, data) {
    return http.put(`/admin/orgs/${id}`, data).then(payload)
  },
  remove(id) {
    return http.delete(`/admin/orgs/${id}`).then(payload)
  },
  migrate(id, data) {
    return http.post(`/admin/orgs/${id}/migrate`, data).then(payload)
  },
  history(id) {
    return http.get(`/admin/orgs/${id}/history`).then(payload)
  },
}

export const distributorApi = {
  list(orgId, params = {}) {
    return http.get(`/admin/orgs/${orgId}/distributors`, { params }).then(payload)
  },
  create(orgId, data) {
    return http.post(`/admin/orgs/${orgId}/distributors`, data).then(payload)
  },
  update(id, data) {
    return http.put(`/admin/distributors/${id}`, data).then(payload)
  },
  resetPassword(id, newPassword) {
    return http.post(`/admin/distributors/${id}/reset-password`, { newPassword }).then(payload)
  },
  setRole(id, orgRole) {
    return http.put(`/admin/distributors/${id}/role`, { orgRole }).then(payload)
  },
}

export const orgQualificationApi = {
  list(orgId) {
    return http.get(`/admin/orgs/${orgId}/qualifications`).then(payload)
  },
  uploadToken(data) {
    return http.post(`/admin/org-qualifications/upload-token`, data).then(payload)
  },
  uploadFile(file) {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/admin/org-qualifications/upload', fd, {
      headers: { 'Content-Type': undefined },
    }).then(payload)
  },
  upload(orgId, data) {
    return http.post(`/admin/orgs/${orgId}/qualifications`, data).then(payload)
  },
  review(qualificationId, data) {
    return http.post(`/admin/org-qualifications/${qualificationId}/review`, data).then(payload)
  },
  history(orgId) {
    return http.get(`/admin/orgs/${orgId}/qualifications/history`).then(payload)
  },
}
