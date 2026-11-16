import http from './http'

const payments = '/admin/mall/payments'
const refunds = '/admin/mall/refunds'
const files = '/admin/mall/files'
const unwrap = (response) => response.data?.data ?? response.data
const headers = (key) => ({ headers: { 'Idempotency-Key': key } })

export const listAdminMallPayments = (params) =>
  http.get(payments, { params }).then(unwrap)
export const getAdminMallPayment = (id) =>
  http.get(`${payments}/${id}`).then(unwrap)
export const queryAdminMallPayment = ({ id, ...body }, key) =>
  http.post(`${payments}/${id}/query`, body, headers(key)).then(unwrap)
export const exportAdminMallPayments = (body, key) =>
  http.post(`${payments}/export`, body, headers(key)).then(unwrap)

export const listAdminMallRefunds = (params) =>
  http.get(refunds, { params }).then(unwrap)
export const getAdminMallRefund = (id) =>
  http.get(`${refunds}/${id}`).then(unwrap)
export const queryAdminMallRefund = ({ id, ...body }, key) =>
  http.post(`${refunds}/${id}/query`, body, headers(key)).then(unwrap)
export const retryAdminMallRefund = ({ id, ...body }, key) =>
  http.post(`${refunds}/${id}/retry`, body, headers(key)).then(unwrap)
export const exportAdminMallRefunds = (body, key) =>
  http.post(`${refunds}/export`, body, headers(key)).then(unwrap)

export const getAdminMallFinanceExport = (id) =>
  http.get(`/admin/mall/finance/exports/${id}`).then(unwrap)
export const getAdminMallFinanceExportFile = (fileId) =>
  http.get(`${files}/${fileId}/access`).then(unwrap)

export const getAdminMallFileAccess = (fileId) =>
  http.get(`${files}/${fileId}/access`).then(unwrap)
