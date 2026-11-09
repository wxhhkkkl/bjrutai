import http from './http'

const root = '/admin/mall/aftersales'
const unwrap = (response) => response.data?.data ?? response.data
const headers = (key) => ({ headers: { 'Idempotency-Key': key } })

export const listAdminAftersales = (params) =>
  http.get(root, { params }).then(unwrap)
export const getAdminAftersale = (id) => http.get(`${root}/${id}`).then(unwrap)
export const getAdminMallRefund = (id) =>
  http.get(`/admin/mall/refunds/${id}`).then(unwrap)
export const decideAftersale = ({ id, ...body }, key) =>
  http.post(`${root}/${id}/decision`, body, headers(key)).then(unwrap)
export const receiveAftersaleReturn = ({ id, ...body }, key) =>
  http.post(`${root}/${id}/receipt`, body, headers(key)).then(unwrap)
export const executeAftersaleRefund = ({ id, ...body }, key) =>
  http.post(`${root}/${id}/execute-refund`, body, headers(key)).then(unwrap)
export const queryAdminMallRefund = ({ id, ...body }, key) =>
  http.post(`/admin/mall/refunds/${id}/query`, body, headers(key)).then(unwrap)
export const retryAdminMallRefund = ({ id, ...body }, key) =>
  http.post(`/admin/mall/refunds/${id}/retry`, body, headers(key)).then(unwrap)
export const getAftersaleProofAccess = (fileId) =>
  http.get(`/admin/mall/files/${fileId}/access`).then(unwrap)
