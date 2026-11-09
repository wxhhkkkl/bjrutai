import http from './http'

function payload(res) {
  return res.data && res.data.data !== undefined ? res.data.data : res.data
}

function list(params = {}) {
  const query = {}
  if (params.cursor) query.cursor = params.cursor
  if (params.pageSize !== undefined) query.pageSize = params.pageSize
  return http.get('/admin/mall/consumptions', { params: query }).then(payload)
}

export const mallConsumptionsApi = { list }
