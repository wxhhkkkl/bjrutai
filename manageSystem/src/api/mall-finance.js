import http from './http'

const payments = '/admin/mall/payments'
const refunds = '/admin/mall/refunds'
const reconciliations = '/admin/mall/reconciliations'
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

export const listMallReconciliations = (params = {}) =>
  http.get(reconciliations, { params }).then(unwrap)
export const getMallReconciliation = (id) =>
  http.get(`${reconciliations}/${id}`).then(unwrap)
export const createMallReconciliation = (body, key) =>
  http.post(reconciliations, body, headers(key)).then(unwrap)
export const closeMallReconciliation = ({ id, ...body }, key) =>
  http.post(`${reconciliations}/${id}/close`, body, headers(key)).then(unwrap)
export const listMallDifferences = (batchId, params = {}) =>
  http.get(`${reconciliations}/${batchId}/differences`, { params }).then(unwrap)
export const addMallDifference = ({ batchId, ...body }, key) =>
  http
    .post(`${reconciliations}/${batchId}/differences`, body, headers(key))
    .then(unwrap)
export const updateMallDifference = ({ id, ...body }, key) =>
  http.patch(`/admin/mall/differences/${id}`, body, headers(key)).then(unwrap)

export function createReconciliationEvidenceUploadState(file) {
  return {
    file,
    ticketKey: crypto.randomUUID(),
    verifyKey: crypto.randomUUID(),
    sha256: null,
    ticket: null,
    uploaded: false,
  }
}

export async function uploadReconciliationEvidence(state) {
  const { file } = state
  const accepted = [
    'application/pdf',
    'image/jpeg',
    'image/png',
    'text/csv',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ]
  if (
    !file ||
    !accepted.includes(file.type) ||
    file.size < 1 ||
    file.size > 10 * 1024 * 1024
  ) {
    throw new Error('请选择不超过 10 MB 的 CSV、XLSX、PDF、JPG 或 PNG 对账证据')
  }
  if (!state.sha256) {
    const digest = await crypto.subtle.digest(
      'SHA-256',
      await file.arrayBuffer()
    )
    state.sha256 = Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, '0')
    ).join('')
  }
  if (!state.ticket) {
    state.ticket = await http
      .post(
        `${files}/upload-ticket`,
        {
          purpose: 'reconciliation_evidence',
          fileName: file.name,
          contentType: file.type,
          fileSize: file.size,
          sha256: state.sha256,
        },
        headers(state.ticketKey)
      )
      .then(unwrap)
  }
  if (!state.uploaded) {
    const target = new URL(state.ticket.uploadUrl)
    if (target.protocol !== 'https:') throw new Error('对账证据上传地址不安全')
    const response = await fetch(target.href, {
      method: 'PUT',
      credentials: 'omit',
      redirect: 'error',
      headers: { 'Content-Type': file.type },
      body: file,
    })
    if (!response.ok) throw new Error('对账证据上传失败，请重试')
    state.uploaded = true
  }
  return http
    .post(`${files}/${state.ticket.fileId}/verify`, null, headers(state.verifyKey))
    .then(unwrap)
}

export const getAdminMallFileAccess = (fileId) =>
  http.get(`${files}/${fileId}/access`).then(unwrap)
